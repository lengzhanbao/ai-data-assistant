# AI 鏁版嵁鍒嗘瀽鍔╂墜锛坅i-data-assistant锛?
> 馃摙 涓€鍙ヨ瘽瀹氫綅锛?*涓婁紶 Excel/CSV锛岀敤涓枃闂竴鍙ワ紝鑷姩鐢熸垚 Pandas 浠ｇ爜銆佺粰鍑虹粨璁轰笌鍥捐〃鈥斺€斾綘鍦ㄦ湰鏈虹鏈夌殑 ChatGPT-for-Data銆?*

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![CI](https://img.shields.io/badge/CI-pending-lightgrey)](https://github.com/lengzhanbao/ai-data-assistant/actions)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

> 鍖归厤鐩爣锛?*灏忕背 路 灏忕埍闊崇绛栫暐杩愯惀瀹炰範鐢?JD** 鈥斺€斻€屾暟鎹垎鏋?/ 寮傚父涓嬫帰 / 浼?SQL 浼樺厛 / 浜嗚В AI agent 鎼缓浼樺厛銆?> 澶嶇敤璧勪骇锛氫綘銆屽府鑰佸笀鐖棰戞暟鎹?+ 澶勭悊鏁版嵁銆嶇殑鐪熷疄鍦烘櫙銆?
## 瀹冭兘鍋氫粈涔?涓婁紶涓€浠?Excel / CSV锛岀敤鑷劧璇█鎻愰棶锛岀郴缁熻嚜鍔細
1. 璁?LLM 鐞嗚В鏁版嵁琛ㄧ粨鏋勶紙鍒椼€佺被鍨嬨€佸墠鍑犺銆佺粺璁℃弿杩帮級
2. 鐢熸垚 Pandas / Matplotlib 浠ｇ爜
3. 鍦?*瀹夊叏娌欑**锛堢嫭绔嬪瓙杩涚▼ + 瀵煎叆鐧藉悕鍗?+ 瓒呮椂缁堢粨锛夐噷鎵ц
4. 杩斿洖**鏂囧瓧缁撹 + 鍥捐〃**锛屽苟灞曠ず鐢熸垚鐨勪唬鐮?
**鏂板锛堝搴斿皬鐖盝D锛夛細**
- 馃攳 **鑷姩娲炲療 / 寮傚父涓嬫帰**锛氫竴閿寜閽紝鑷姩浜у嚭銆屾暟鎹€昏 + 寮傚父鐐瑰畾浣?+ 杩愯惀寤鸿銆嶏紙JD 鍏抽敭璇嶏細鏁版嵁鍒嗘瀽 / 寮傚父涓嬫帰锛?- 馃梽锔?**绛変环 SQL 瀵圭収**锛氭瘡涓垎鏋愬悓鏃剁炕璇戞垚 SQL 灞曠ず锛圝D 鍏抽敭璇嶏細浼?SQL 浼樺厛锛?- 鈿狅笍 LLM 鏈厤缃椂椤甸潰椤堕儴鍙嬪ソ鎻愮ず锛?health 鎺㈡祴锛?- 馃挕 绀轰緥闂涓€閿偣鍑伙紙chips锛夛紝鏃犻渶鎵撳瓧

绀轰緥闂锛堢敤 `sample_data/video_stats.csv` 鐩存帴璇曪級锛?- 鍝釜瑙嗛瀹屾挱鐜囨渶楂橈紵
- 鎾斁閲忔渶楂樼殑 5 涓棰戞槸鍝簺锛?- 鎸夊彂甯冩棩鏈熺敾鎾斁閲忚秼鍔垮浘
- 浜掑姩鐜囧拰瀹屾挱鐜囩殑鐩稿叧鎬у浣曪紵
- 鐐广€岎煍?鑷姩娲炲療銆嶇湅寮傚父涓嬫帰鏁堟灉

## 杩愯
```bash
pip install -r requirements.txt

# 閰嶇疆 LLM锛圤penAI 鍏煎鍗忚锛屽彲鐢ㄤ綘宸叉湁鐨?opencode / glm / deepseek 绔偣锛?export LLM_BASE_URL="https://浣犵殑绔偣/v1"
export LLM_API_KEY="浣犵殑key"
export LLM_MODEL="妯″瀷鍚?

python app.py
# 鎵撳紑 http://127.0.0.1:5000 锛屼笂浼?sample_data/video_stats.csv 鍗冲彲浣撻獙
```

鑷 LLM 杩為€氭€э細`python llm_client.py`

## 宸ョ▼瑕佺偣锛堥潰璇曞彲璁诧級
| 鐐?| 鍋氭硶 |
|----|------|
| 娌欑闅旂 | `multiprocessing` 鐙珛杩涚▼锛岃秴鏃?`terminate`锛屼笉姹℃煋涓昏繘绋?|
| 瀹夊叏 | 瀵煎叆鐧藉悕鍗?+ 鍙楅檺鍐呯疆鍑芥暟锛岀 `os/subprocess/socket` |
| 瀹归敊 | LLM 鐢熸垚浠ｇ爜鎵ц鎶ラ敊 鈫?鑷姩鎶婃姤閿欏洖鐏?LLM 淇涓€娆?|
| 鍙В閲?| 鍓嶇灞曠ず鐢熸垚鐨勪唬鐮侊紝缁撴灉鍙拷婧?|
| 鏁版嵁鎺ュ彛 | 鏁版嵁闆嗕互鍙橀噺 `df` 娉ㄥ叆锛屼唬鐮佹棤娉曡纾佺洏鍏朵粬鏂囦欢 |

## 瀵瑰簲灏忕背 JD 鐨勮瘽鏈?- 銆屾暟鎹垎鏋?/ 寮傚父涓嬫帰銆嶁啋 涓€閿€岃嚜鍔ㄦ礊瀵熴€嶏細涓婁紶涓氬姟琛紝鑷姩浜у嚭 鎬昏/寮傚父/寤鸿锛坺-score 瀹氫綅浣庡畬鎾巼瑙嗛绛夛級
- 銆屼細 SQL 浼樺厛銆嶁啋 姣忎釜鍒嗘瀽鑷姩闄?*绛変环 SQL**锛屽睍绀轰綘鎳傜粨鏋勫寲鏌ヨ锛圥andas 鈫?SQL 鍙岃鑳藉姏锛?- 銆屼簡瑙?AI agent 鎼缓浼樺厛銆嶁啋 鏈」鐩槸 Agent 鑼冨紡锛歀LM 鍐崇瓥 鈫?璋冪敤宸ュ叿锛堜唬鐮佹墽琛岋級鈫?瑙傚療缁撴灉 鈫?淇閲嶈瘯锛屼笌浣犵殑 QQBot Agent 鍚屾簮

## 鏂囦欢缁撴瀯
```
app.py             Flask 鏈嶅姟锛堜笂浼?/ 鎻愰棶 / 鑷姩娲炲療 / 鍑哄浘 / health锛?analyzer.py        鍒嗘瀽寮曟搸锛歀LM 鐢熸垚浠ｇ爜 + 娌欑鎵ц + 鑷姩閲嶈瘯 + SQL 缈昏瘧
sandbox.py         瀹夊叏娌欑锛堢嫭绔嬪瓙杩涚▼ + 鐧藉悕鍗?+ 瓒呮椂锛?runner.py          娌欑瀛愯繘绋嬭繍琛岃剼鏈紙涓枃瀛椾綋閰嶇疆鍦ㄦ锛?llm_client.py      OpenAI 鍏煎 LLM 瀹㈡埛绔?templates/index.html  鍗曢〉 UI锛堢ず渚媍hips / 娲炲療鎸夐挳 / SQL鎶樺彔锛?sample_data/       绀轰緥瑙嗛鏁版嵁锛堝搴斾綘甯€佸笀鐖殑鏁版嵁锛?test_sandbox.py    娌欑绂荤嚎娴嬭瘯
test_app.py        绔埌绔?Web 娴嬭瘯锛堝亣 LLM锛?```
