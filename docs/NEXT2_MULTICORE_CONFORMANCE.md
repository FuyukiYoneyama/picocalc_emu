# NEXT-2A PicoCalc multicore conformance契約

**状態:** 実装前契約を凍結。アプリ、firmware target、backend修正より先に固定する。

## 目的

backend内部にはRP2040 core 1、SIO FIFO、WFE/SEV、IRQ_PROC1のモデルとRust単体試験があるが、
実際のPico SDK firmwareがcore 1を起動する正式targetはまだない。NEXT-2Aでは新規app
`PicoCalc Multicore Conformance`を使い、SDKの公開APIから次の縦断を一つのBINで検証する。

1. `multicore_launch_core1()`による6-word bootrom互換launch
2. 双方向SIO FIFOの固定4-vector変換
3. core 1のWFE待機とcore 0のSEVによる再開
4. FIFO到着によるSIO_IRQ_PROC1 deliveryとWFEからのIRQ wake

NEXT-2BのDMA-paced PCM sample sinkは別契約とする。multicoreが動いたことをaudio出力の証拠には
使わない。

## 凍結baseline

- `picocalc_emu`: `76334780b2c5d7854c4707d7ce963f971b0a39c8`
- 最初のrunに使うpromoted backend: `e985a9d7ecb51ef760506a105edd34e31cf9b5f1`
- Pico SDK 2.2.0: `a1438dff1d38bd9c65dbd693f0e5db4b9ae91779`
- ARM GCC 13.2.1、CMake 3.28.3、Ninja 1.11.1
- Serial、quantum 1、PIO RGB565

機械可読正本は
[`next2-multicore-v1.json`](../firmware-validation/contracts/next2-multicore-v1.json)である。

## 固定phase

### Launch

core 0はSDKの`multicore_launch_core1()`だけを使ってcore 1を起動する。アプリからemulator内部状態や
core 1のPC/SPへ触れない。core 1は最初に`0xc0110001`をFIFOへ返す。

### FIFO

core 0は次の4語を順に送り、core 1は
`rotate_left_32(input XOR 0xa5a55a5a, one_based_index)`を返す。

| input | output |
|---:|---:|
| `0x00000000` | `0x4b4ab4b5` |
| `0x12345678` | `0xde44308a` |
| `0xffffffff` | `0xd2d52d2a` |
| `0x0badcafe` | `0xe0890a4a` |

### WFE/SEV

core 1は共有stageを1にして`0xc0111001`を通知した後WFEへ入る。core 0は短い待機後もstageが1で
あることを確認してSEVを発行する。core 1はstageを2にし、`0xc0111002`を返す。

### IRQ_PROC1

core 1はSIO_IRQ_PROC1 handlerを登録・enableし、`0xc0112001`を通知してWFEへ入る。core 0が
`0x13579bdf`をFIFOへ送ると、handlerが1回だけ受信・記録する。core 1は
`0xc0112002`を返し、IRQ count 1と受信値をcore 0が照合する。

## Fail-closed規則

次の5 markerがすべてなければPASSにしない。

```text
[NEXT2][MC][LAUNCH] status=pass ready=0xc0110001
[NEXT2][MC][FIFO] status=pass vectors=4
[NEXT2][MC][WFE_SEV] status=pass before=1 after=2
[NEXT2][MC][IRQ_PROC1] status=pass count=1 word=0x13579bdf
[NEXT2][MC][VERDICT] launch=pass fifo=pass wfe_sev=pass irq_proc1=pass overall=pass
```

exception、unsupported MMIO、marker不足、cycle limit前の未完了をPASSにしない。core 1のNMIまたは
HardFaultも正式targetではfailureにする。最初のrunは凍結backendを変更せず行い、成功・失敗を問わず
保存する。backend gapが見つかった場合は元runを保持し、修正版を新revisionとして検証する。

## 正式化と実機相関

clean cloneからBIN/UF2を2回再現し、firmware run 3回のUART、report、timelineを一致させる。
その後、同じbuildのUF2をPicoCalcへ書き込み、人間のキー操作なしでUART全文と最終PASS写真1枚を
保存する。`emulator PASS -> hardware FAIL`は破棄せず、NEXT-3のfalse acceptとして扱う。

この契約はSerialだけを対象とする。Threaded、両core同時LCD/PSRAM、spinlock timing、core 1再launch、
DMA-paced PCMは合格範囲外である。
