# 本機語音轉文字模型評估

評估日期：2026-10-31。目的是替「本地影片」選一個不用金鑰、不用雲端，也不需要顯示卡的語音轉文字模型。

## 測試條件

- 電腦：Intel Core i5-12400F，32 GB 記憶體。全部只用 CPU，6 個執行緒。
- 中文與英文長段落：Windows 內建語音合成（`Microsoft Hanhan`、`Microsoft Zira`）唸出已知文稿，分別 142.6 秒和 72.5 秒。
- 真人短句：SenseVoice 模型附的 `zh.wav`（5.6 秒）和 `en.wav`（7.2 秒）。
- 錯誤率：先轉成台灣繁體並移除標點，中文算字元編輯距離，英文算單字編輯距離。阿拉伯數字和中文數字視為不同，所以「9 點」和「九點」會計入錯誤。

## 結果

| 模型 | 模型大小 | 速度（幾倍即時） | 記憶體（RSS） | 中文語音合成錯誤率 | 英文語音合成錯誤率 | 真人中文 | 真人英文 |
|---|---|---|---|---|---|---|---|
| **SenseVoiceSmall int8** | 240 MB | **約 31 倍** | **約 80 MB** | 3.0% | 5.2% | 23.1%（13 字錯 3 字） | 0% |
| faster-whisper `small` | 464 MB | 約 10 倍 | 約 500 MB | 1.5% | 1.0% | 15.4%（數字寫法） | 0% |
| faster-whisper `large-v3-turbo` | 1.6 GB | 約 3 倍 | 約 1.5 GB | 2.6% | 1.0% | 0% | 0% |

真人短句太短，表內的速度只取長段落。Whisper 在極短音訊上的耗時主要花在載入和語言偵測，不代表長影片的速度。

## 決定

預設採用 **SenseVoiceSmall int8（透過 sherpa-onnx）**：

- 一小時影片在這台電腦約兩分鐘可轉完，沒有顯示卡的電腦也能接受。
- 記憶體和模型都最小，適合免安裝版；模型在使用者按下時才下載，並比對 SHA-256。
- 代價是準確度較低：真人中文短句把「開放」聽成「開飯」，英文也有明顯較多錯字。介面會標示「可能有錯字」。

## 這份評估的限制

- 語音合成的發音清楚、沒有背景音，**真實影片的錯誤率一定更高**。這裡的數字只適合比較模型，不代表實際品質。
- 真人樣本只有兩句，沒有測口音、多人對話、背景音樂或長時間教學影片。
- 只測了一台電腦；CPU 較弱的筆電速度會明顯較慢。
- 之後應該用幾支有權使用的真實影片重新比較。如果錯字太多，可以再加入 `small` 當作「較準但較慢」的選項。

## 授權

- SenseVoice 模型：FunASR Model License 1.1，可使用、複製、修改和分享，但要標示來源與作者並保留模型名稱；模型「按現狀」提供。
- sherpa-onnx：Apache-2.0。
- Silero VAD：MIT。
- PyAV：BSD-3-Clause，內含的 FFmpeg 另有授權。

公開發布前仍要再確認完整授權清單，見 [Beta 發布門檻](BETA_READINESS.zh-TW.md)。

## 來源

- [FunASR 模型授權](https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE)
- [SenseVoice](https://github.com/FunAudioLLM/SenseVoice)
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
