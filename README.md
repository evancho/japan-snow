# 日本雪場

用繁體中文看日本滑雪場的積雪、新雪和未來幾天的降雪。給手機用，打開就能搜。

公開網址（合併到 `main` 並打開 GitHub Pages 之後）：

**https://evancho.github.io/japan-snow/**

不用登入，也不用自己的電腦開著。頁面是靜態的，雪況寫在 `data/conditions.json`，由 GitHub Actions 定期更新。

## 怎麼用

- 搜尋可以打中文、日文漢字、平假名、片假名，或英文、羅馬拼音。例如 `二世谷`、`ニセコ`、`にせこ`、`niseko`、`白馬`、`hakuba`。
- 上面的地區可以篩：北海道、東北、關東甲信、新潟、北陸、東海、關西、中國、四國、九州。
- 可以依積雪、24 小時新雪、48 小時新雪、未來 3 日預報或名稱排序。
- 星星會把雪場收到「收藏」，存在這台裝置的 localStorage，重新打開還在，並排在清單上面。
- 網址可以分享。例如：
  - 單一雪場：`https://evancho.github.io/japan-snow/#/r/niseko-united`
  - 篩過的清單：`https://evancho.github.io/japan-snow/#/?region=hokkaido&sort=d24&q=二世谷`

11 月到 12 月中旬，頁面會提示多數雪場還沒開季。數字是積雪和預報，不代表已經在營業。

## 資料從哪來

| 資料 | 來源 | 授權 |
| --- | --- | --- |
| 降雪、氣溫、積雪估計、未來幾天的預報 | [Open-Meteo](https://open-meteo.com/) 預報 API | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| 有鄰近測站、而且雪季有在報的時候，積雪深度和 24 小時新雪改用實測 | [氣象廳 AMeDAS](https://www.jma.go.jp/bosai/amedas/) | 氣象廳網站內容依政府公共資料利用條款（與 CC BY 4.0 相容）。這裡有挑選測站、換算單位，不是原始畫面。 |
| 雪場名稱與座標 | [OpenStreetMap](https://www.openstreetmap.org/copyright) | ODbL。`data/resorts.json` 是由此整理的衍生資料。 |
| 用來判斷雪場在哪個都道府縣 | [地球地圖日本](http://www.gsi.go.jp/kankyochiri/gm_jpn.html) 的都道府縣界（建置清單時使用，沒有放進網站） | 非營利用途需註明出典。 |

頁尾也有同樣的出處。

實測和估計會分開標。測站太遠，或標高和雪場差太多，列表仍用模式估計，詳情裡會附上測站數字。11 月前後，AMeDAS 的積雪計很多還沒開始報，這段時間幾乎都會標成估計。

這不是氣象廳的正式預報，也不能拿來代替雪場公告。氣象業務法對在日本提供預報服務另有規定；本站只是把上述來源整理給台灣的朋友看。

## 更新頻率

GitHub Actions 工作流程「發布日本雪場」（`.github/workflows/pages.yml`）：

- 合併到 `main` 時，用倉庫裡現有的 JSON 發布網站。
- 每 3 小時（UTC 的第 20 分，`20 */3 * * *`）抓一次新雪況，寫回 `data/conditions.json`，再發布。一天 8 次。
- 也可以到 Actions 頁面手動跑。

Open-Meteo 免費 API 供非商業使用。請維持這個頻率，不要改成每幾分鐘打一次。

## 合併之後要自己點一次

GitHub 不會自動把 Pages 的來源改成 Actions，請在倉庫設定裡打開：

1. **Settings → Pages → Build and deployment → Source**，選 **GitHub Actions**。
2. 到 **Actions** 看「發布日本雪場」。如果停在等待核准 `github-pages` 環境，按核准。
3. 若排程提交失敗、寫不回 `main`，到 **Settings → Actions → General → Workflow permissions**，選 **Read and write permissions**。
4. 跑完之後打開 https://evancho.github.io/japan-snow/ 。第一次發布可能要等一兩分鐘。

## 本地預覽

```bash
python3 scripts/build_resorts.py   # 需要網路，會重抓雪場清單
python3 scripts/fetch_conditions.py
python3 scripts/check_data.py
python3 -m http.server 8765
```

瀏覽器開 http://127.0.0.1:8765/ 。

`build_resorts.py` 平常不用跑。雪場清單已經在 `data/resorts.json`。只有要補新雪場時才重建。

## 目前的範圍與限制

- 雪場約 500 座，來自 OpenStreetMap 的滑雪場範圍，含大型雪場和不少町營小雪場。不是官方名冊，可能有漏，也可能有已歇業的。
- 常見雪場用台灣習慣的叫法（二世谷、留壽都、白馬八方尾根、野澤溫泉、藏王溫泉等）。其餘由日文漢字轉繁體；片假名地名能對上的用常見譯名，對不上的用音譯。小雪場的中文名偶爾會生硬，日文原名會列在旁邊。
- 二世谷（比羅夫、二世谷村、安努普利、花園）在地圖上是同一片山，雪況共用一筆。
- 座標是雪場範圍的中心，不是山頂，也不是旅館。模式標高寫在詳情裡。
- 沒有即時的營業、纜車、壓雪狀態。
- 預報是模式結果，山區會有誤差。
- Actions 的排程有時會晚幾分鐘到幾十分鐘。
