# NEXT-3 SD CMD8 CRC candidate

**状態（2026-08-10）:** A1正常対照はemulatorと実機がPASSした。Fault Bは再現可能artifactとして固定し、
uf2loader実機先行runが凍結oracleへ完全一致した。凍結backend `4a908648`で同一BINを初回実行した結果、
backendは不正CRCを受理してapp PASSとなり、`false_accept`を確定した。初回結果の保存・分類が完了したため、
次は新しいbackend revisionへCMD8 CRC7 rejectionを実装する。機械可読な正典は
`firmware-validation/contracts/next3-sd-cmd8-crc-v1.json`である。

## なぜLCD候補から切り替えるか

LCD v1/v2は再現可能artifactを作れたが、2回とも凍結した歴史的oracleより広いrotated-bit症状となった。
旧BIN、正確なSDK/toolchain、runtime条件を回収できず、差分を重ねて古い見た目へ合わせても同一欠陥の証明に
ならない。このためLCD候補は`inconclusive`で閉じた。

次候補は表示のsampling phaseや人のキー入力へ依存せず、protocolが理由を直接返すものを選ぶ。SD SPIの
CMD8 CRC errorはこの条件を満たす。

## 仕様と現行source

SD AssociationのPhysical Layer Simplified Specification、section 7.2.2は、SPI modeが既定でCRC OFFでも
CMD8のCRC検査は常時有効であり、不正CRCにはR1のCRC errorを返すと定める。

- 公式仕様:
  `https://www.sdcard.org/cms/wp-content/themes/sdcard-org/dl.php?f=Part1_Physical_Layer_Simplified_Specification_Ver5.10.pdf`
- canonical BSPはCMD8 `0x000001aa`へ正しいCRC byte `0x87`を送る。
- backend `4a908648`は6 byte commandのCRC byteを無条件に捨て、CRCに関係なくCMD8へ正常R7を返す。

よってBSPのCMD8 CRCだけを`0x87`から`0x85`へ変えると、実機はCRC errorで初期化を止める一方、現行
backendは正常に進める可能性が高い。これはfalse acceptの**事前予測**であり、結果ではない。faultの実機
oracle一致前にBINをemulatorへ投入せず、初回結果を見てから期待を変更しない。

`0x85`はCRC byteのend bitを1のまま維持し、CRC7だけを正しい`0x87`から変える。そのためframe終端や
command argumentの欠陥と混同しない。

## application設計

新しい独立repository `picocalc-next3-sd-crc-fault`へ、最小のSD初期化diagnosticを作る。既存のLCD fault
repositoryへ別種類の候補を混在させない。

applicationは次だけを行う。

1. boot/source/build identityをUARTへ出す。
2. card detectを確認する。
3. 80 idle clocks、CMD0、CMD8を含むcanonical `sdcard::init()`を実行する。
4. CMD0とCMD8についてcommand、argument、CRC、R1、R7を機械可読markerへ出す。
5. 安定した最終状態を画面とUARTへ反復表示する。

FatFs mount、format、file read/write/removeは行わない。したがって32 GB実カードと64 MiB emulator cardの
FAT geometry、空き容量、既存fileは判定へ影響しない。キー入力も不要である。

## A-B-Aと変更予算

| 版 | CMD8 CRC | 期待 |
|---|---:|---|
| A1 baseline | `0x87` | emulator PASS、実機R1=`0x01`／R7=`000001aa`、init PASS |
| B fault | `0x85` | 実機R1=`0x09`（idle＋COM_CRC_ERROR）、CMD8段階でFAIL |
| A2 fixed | `0x87` | A1と同じartifact hashと結果 |

A1からBで変更してよいのはapplication identity、evidence marker、CMD8 CRC literalの3点だけである。
CMD0、argument、SPI clock/mode、CS、polling、timeout、R7判定、backendは変更しない。

実装監査では、送信CRCだけでなく`app/main.cpp`のexpected command-trace CRCも`0x85`へ変える。これを
`0x87`のままにすると、backend応答を見る前にapplicationが自分で注入したCRCを拒否し、false acceptを
測れないためである。PASSにはtraceが`0x85`であることに加え、正常R1/R7とinit成功も必要なので、実機の
CRC rejectionは引き続きFAILとなる。実行に影響しないREADMEと局所契約文書はこの差分とhardware-first境界だけを
記述する。

A2はfault CRCを正しい値へ戻すだけである。A1とBIN/UF2がbyte一致するなら、A1の実機PASSが同一artifactの
fixed証拠でもあるため、同じUF2を3回目に人が起動する必要はない。hashが一致しなければA2を別artifactとして
実機確認する。

## A1固定結果

A1は独立repository `picocalc-next3-sd-crc-fault`のcommit
`f942b8eb000858e6f00bb8fde255f27243dfbac8`へ固定した。source repositoryと別clean cloneから、固定時刻
`2026-08-10T05:00:00Z`、Pico SDK 2.2.0 commit `a1438dff...`、GCC 13.2.1、CMake 3.28.3、
Ninja 1.11.1で次のartifactを再現した。

- BIN SHA-256: `0ae9eea01f87c542cd7c41f1880c42d428c0f143c909dfe116c16e1cf5afce1b`
- UF2 SHA-256: `be9c0e8deda02307e34a96c11cec21255f1e197902920d1fe8e05f9d472a9ffd`
- source bundle SHA-256: `ed985de566638e07e0a20e974b351646729b434a6bb05edd349dc5fb162a05da`

同一BINを凍結backend `4a908648`で実行し、CMD0 R1=`0x01`、CMD8 argument=`000001aa`、
CRC=`0x87`、R1=`0x01`、R7=`000001aa`、init PASSを確認した。FAT32 card modelは接続したが、block read/writeは
ともに0でfilesystemへアクセスしていない。exceptionとunsupported MMIOも0、scenarioと最終緑画面もPASSした。
証拠は`firmware-validation/records/next3-sd-cmd8-crc-a1-20260810-01/`にある。

同一UF2をuf2loaderから実機で起動し、boot/source/build identity、card detect、CMD0
arg=`00000000`／CRC=`0x95`／R1=`0x01`、CMD8 arg=`000001aa`／CRC=`0x87`／R1=`0x01`／
R7=`000001aa`、initとappのPASSを確認した。完全なEVIDENCE markerは39回すべて同一で、写真も白い上部と
緑の中央・下部を示した。repository保存写真はmetadataを除去し、元写真とのdecoded RGB SHA一致を確認した。
実機記録は
`firmware-validation/records/next3-sd-cmd8-crc-a1-hardware-20260810-01/`にある。

これでA1 gateは完了し、CRC `0x85`のFault B source実装を許可する。ただしFault BINをemulatorへ入れては
ならず、まず再現可能artifactを固定し、同一UF2をuf2loader実機で先行実行する。

## Fault B固定結果

Fault Bはcommit `e78cabbe20416eb2347e0db09408bf906d41c698`へ固定した。実行差分は
`CMakeLists.txt`のidentity、`app/main.cpp`のEVIDENCE namespaceとexpected trace CRC、
`bsp/src/sdcard.cpp`の送信CRCだけである。CMD0、CMD8 argument、SPI、CS、polling、R7、timeout、filesystem、
keys、backendは変えていない。source本体と独立clean cloneは固定時刻`2026-08-10T05:30:00Z`で一致した。

- BIN SHA-256: `6665ca51944e2c1fb2f7e2ba7adb01ce6878290aac0dfb929202714b83509bd0`
- UF2 SHA-256: `43ea10982d6f9b1d1adf9565b2b88f8b1866ddd60410b4ae53fda8e2f9a3e958`
- source bundle SHA-256: `3e3fded89db4d4feb9a0d1c810d388e18ccc49c698ab466a371e3c2c94f1739a`

記録は`firmware-validation/records/next3-sd-cmd8-crc-b-20260810-01/`にある。

同一UF2のuf2loader実機runはCMD0 R1=`0x01`、CMD8 CRC=`0x85`／R1=`0x09`、init
`cmd8_fail detail=9`、filesystemなし、app FAILとなり、凍結oracleへ完全一致した。EVIDENCE markerは46回
同一で、写真も白い上部と赤い中央・下部を示した。記録は
`firmware-validation/records/next3-sd-cmd8-crc-b-hardware-20260810-01/`にある。これで初回Fault emulator
runを解禁した。

同一BINを凍結backend `4a908648`で1回だけ実行したところ、CMD8 CRC=`0x85`に対して正常R1=`0x01`と
R7=`000001aa`を返し、initとappがPASSした。実機のCMD8 CRC rejectionと一致しないため、分類は
`false_accept`である。初回runは
`firmware-validation/records/next3-sd-cmd8-crc-b-first-emulator-20260810-01/`へ固定した。outcomeに依存しない
EVIDENCE prefix停止のためUART末尾は反復markerの途中だが、完全なCMD8、init、RESULT、structured verdict、
緑のsnapshotが揃っており分類に不足はない。初回runを再実行・置換しない。

この限定datasetのnegative母数は1、正検出0/1、false accept 1/1となった。一般的なエミュレーター品質率を
意味しない。positive相関は7系列のままである。

## 凍結した実機oracle

Bは次の全条件を満たす場合だけhardware-confirmed negative caseへ入る。

- uf2loaderから起動し、boot identityと凍結UF2が一致する。
- card detectはpresent、CMD0はR1=`0x01`で成功する。
- CMD8はargument `000001aa`、送信CRC `0x85`、R1=`0x09`となる。
- R1はidleとCOM_CRC_ERRORだけを示し、illegal command、address error、parameter errorを含まない。
- `sdcard::init()`はCMD8段階でFAILし、CMD55／ACMD41／CMD58へ進まない。
- filesystemへ一切アクセスせず、最終`app=fail` markerが安定反復する。
- exception、unsupported MMIO、cycle limit、UART欠落、identity不一致はない。

1 fieldでも違えば`inconclusive`としてそのまま保存し、oracleを変更せず、fault BINをemulatorで実行しない。
同じoracle mismatchを繰り返すhardware retryも行わない。

## 初回emulator runとbackend修正の境界

実機Bがoracleへ完全一致した後だけ、同一BINをbackend commit `4a908648`で1回実行する。現行modelはCRCを
捨てるためPASSが予測されるが、PASSでもFAILでも初回recordを保存してから分類する。

初回runは`false_accept`として保存・分類済みであり、backend変更禁止境界は完了した。次はbackendへCMD8
CRC7検査とR1 COM_CRC_ERRORを実装する。修正後は同じfault BINが同じ理由でFAILし、A1と既存positive
targetがexact contractを保つことをローカルで検証する。GitHub Actionsは使わない。

## 人間操作とリカバリ

通常必要な実機操作は2回だけである。

1. A1 UF2をuf2loaderから1回起動し、UART全文と安定後の写真1枚を保存する。
2. B UF2をuf2loaderから1回起動し、UART全文と安定後の写真1枚を保存する。

押すべきapplication key、連続入力、時間指定写真はない。captureにidentityがない、UARTが途中で切れた、という
**測定失敗だけ**は同じartifactを最大1回再実行する。oracleと違う有効な結果は再試行せず証拠として採用する。
BOOTSEL限定の理由はなく、一般利用経路のuf2loaderをprimaryとする。

A1とBの2回の人間操作は完了し、追加の実機操作は現段階では不要である。

## CI方針

設計、build、emulator、schema、回帰はローカルで行う。実装前契約のためにpushやGitHub Actionsを起動しない。
workflowは変更しない。
