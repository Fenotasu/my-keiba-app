import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import requests
from bs4 import BeautifulSoup
import time

# --- ページ設定 ---
st.set_page_config(page_title="当日大口流入・総括まとめ", layout="wide")

# --- データ取得関数 ---
def get_real_odds(race_id):
    # オッズページ(直前想定)と結果ページ(確定後)の両方をチェック
    urls = {
        "before": f"https://race.netkeiba.com/race/odds.html?race_id={race_id}",
        "after": f"https://race.netkeiba.com/race/result.html?race_id={race_id}"
    }
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    results = {}

    for key, url in urls.items():
        try:
            res = requests.get(url, headers=headers, timeout=5)
            res.encoding = res.apparent_encoding
            soup = BeautifulSoup(res.text, 'html.parser')
            rows = soup.select('tr.HorseList')
            if not rows: continue
            
            data = []
            for row in rows:
                name_tag = row.select_one('.HorseName') or row.select_one('.Horse_Name')
                win_tag = row.select_one('.WinOdds') or row.select_one('.Odds')
                place_tag = row.select_one('.PlaceOdds')
                
                if not name_tag or not win_tag: continue
                
                name = name_tag.text.strip()
                win = win_tag.text.strip().replace('---', '0').replace('取消', '0')
                place = place_tag.text.split('-')[0].strip() if place_tag else "0.0"
                
                try:
                    win_f, place_f = float(win), float(place)
                    if win_f <= 0: continue
                    data.append({"馬名": name, "単勝": win_f, "複勝": place_f})
                except: continue
            results[key] = pd.DataFrame(data)
        except: continue
    return results

# --- メイン画面 ---
st.title("🏆 本日の大口流入馬・総括ベスト10")
st.markdown("1日の終わりに、全レースの「締め切り直前の動き」を自動でまとめて答え合わせします。")

# サイドバー
st.sidebar.header("⚙️ 解析設定")
# 今週末の開催コード例（2026年 東京:05, 京都:08, 小倉:10）
date_code = st.sidebar.text_input("開催日コード (8桁)", value="20260501")
venues = st.sidebar.multiselect("会場コード", ["05", "08", "10"], default=["05", "08"])
st.sidebar.caption("05:東京, 08:京都, 10:小倉")

if st.sidebar.button("本日の全レースを一括解析"):
    all_abnormal_data = []
    progress_bar = st.progress(0)
    
    total_steps = len(venues) * 12
    step = 0

    status_text = st.empty()

    for v in venues:
        for r in range(1, 13):
            step += 1
            race_no = str(r).zfill(2)
            race_id = f"{date_code}{v}{race_no}"
            status_text.text(f"解析中: {v}会場 {r}R (ID:{race_id})...")
            
            res = get_real_odds(race_id)
            # 両方のページからデータが取れた場合のみ比較（＝レース終了後）
            if "before" in res and "after" in res:
                df_b, df_a = res["before"], res["after"]
                merged = pd.merge(df_a, df_b, on="馬名", suffixes=('_確定', '_直前'))
                
                # 下落率の計算
                merged['下落率'] = (merged['複勝_直前'] - merged['複勝_確定']) / merged['複勝_直前']
                merged['会場R'] = f"{v}会場 {r}R"
                all_abnormal_data.append(merged)
            
            progress_bar.progress(step / total_steps)
            time.sleep(0.2) # 相手サーバーへの負荷軽減（重要）

    if all_abnormal_data:
        final_df = pd.concat(all_abnormal_data)
        # 異常値（下落率）が高い順に並べ替え
        top10 = final_df.sort_values('下落率', ascending=False).head(10)
        st.session_state['top10'] = top10
        status_text.success("すべての解析が完了しました！")
    else:
        status_text.error("データが取得できませんでした。レース終了後にお試しください。")

# --- 結果表示 ---
if 'top10' in st.session_state:
    df = st.session_state['top10']
    
    st.subheader("🔥 本日の「複勝」大口流入ランキング")
    st.info("締め切り直前にオッズが急落した（＝大量投票された）馬のトップ10です。")

    # 上位3頭をカード形式で
    top_cols = st.columns(3)
    for i in range(min(3, len(df))):
        row = df.iloc[i]
        with top_cols[i]:
            st.warning(f"RANK {i+1}")
            st.metric(label=f"{row['会場R']} : {row['馬名']}", 
                      value=f"確定 {row['複勝_確定']:.1f}", 
                      delta=f"下落率 -{row['下落率']*100:.1f}%")

    st.divider()
    
    # 全体グラフ
    fig = px.bar(df, x='下落率', y='馬名', color='下落率',
                 hover_data=['会場R', '複勝_直前', '複勝_確定'],
                 text='会場R', orientation='h',
                 title="本日の中央競馬・異常オッズ総括ランキング",
                 color_continuous_scale='Reds')
    st.plotly_chart(fig, use_container_width=True)
    
    # データテーブル
    st.subheader("📋 解析データ詳細")
    st.dataframe(df[['会場R', '馬名', '複勝_直前', '複勝_確定', '下落率']].style.format({'下落率': '{:.1%}'}))

else:
    st.info("1日の終わりにサイドバーのボタンを押してください。その日の全36レース（最大）を自動解析します。")
