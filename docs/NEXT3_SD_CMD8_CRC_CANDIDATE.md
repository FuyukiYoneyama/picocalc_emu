# NEXT-3 SD CMD8 CRC candidate

**状態（2026-08-10）:** 実装前契約を固定した。fault実装、実機run、fault BINのemulator run、backend修正は
まだ行っていない。機械可読な正典は
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

A2はfault CRCを正しい値へ戻すだけである。A1とBIN/UF2がbyte一致するなら、A1の実機PASSが同一artifactの
fixed証拠でもあるため、同じUF2を3回目に人が起動する必要はない。hashが一致しなければA2を別artifactとして
実機確認する。

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

false acceptなら、その時点で初めてbackendへCMD8 CRC7検査とR1 COM_CRC_ERRORを実装する。修正前に
初回runを消したり、backendを先回りして直したりしない。修正後は同じfault BINが同じ理由でFAILし、A1と
既存positive targetがexact contractを保つことをローカルで検証する。

## 人間操作とリカバリ

通常必要な実機操作は2回だけである。

1. A1 UF2をuf2loaderから1回起動し、UART全文と安定後の写真1枚を保存する。
2. B UF2をuf2loaderから1回起動し、UART全文と安定後の写真1枚を保存する。

押すべきapplication key、連続入力、時間指定写真はない。captureにidentityがない、UARTが途中で切れた、という
**測定失敗だけ**は同じartifactを最大1回再実行する。oracleと違う有効な結果は再試行せず証拠として採用する。
BOOTSEL限定の理由はなく、一般利用経路のuf2loaderをprimaryとする。

## CI方針

設計、build、emulator、schema、回帰はローカルで行う。実装前契約のためにpushやGitHub Actionsを起動しない。
workflowは変更しない。
