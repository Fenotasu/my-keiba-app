import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import requests
from bs4 import BeautifulSoup

# --- ページ設定 ---
st.set_page_config(page_title="競馬異常オッズ監視アプリ", layout="wide")

# --- データ取得関数（スクレイピング） ---
# --- 12行目付近からここを貼り付け ---
def get_real_odds(race_id):
    # オッズページ（直前用）と結果ページ（事後用）の両方をチェック
    urls = [
        f"https://race.netkeiba.com/race/odds.html?race_id={race_id}",
        f"https://race.netkeiba.com/race/result.html?race_id={race_id}"
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    
    for url in urls:
        try:
            res = requests.get(url, headers=headers)
            res.encoding = res.apparent_encoding
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 馬のリスト（行）を取得
            rows = soup.select('tr.HorseList') 
            if not rows:
                continue # 見つからない場合は次のURLへ

            data = []
            for row in rows:
                # オッズページ用と結果ページ用、両方のタグ名に対応させる
                name_tag = row.select_one('.HorseName') or row.select_one('.Horse_Name')
                win_tag = row.select_one('.WinOdds') or row.select_one('.Odds')
                place_tag = row.select_one('.PlaceOdds')
                
                if not name_tag or not win_tag:
                    continue

                name = name_tag.text.strip()
                win_val = win_tag.text.strip().replace('---', '0').replace('取消', '0')
                
                # 複勝の処理
                if place_tag:
                    place_val = place_tag.text.split('-')[0].strip()
                else:
                    # 結果ページなどで複勝がない場合は単勝の25%で仮計算
                    place_val = str(round(float(win_val) * 0.25, 1)) if win_val.replace('.','').replace(',','').isdigit() else "0.0"

                try:
                    win_f = float(win_val)
                    place_f = float(place_val)
                    if win_f <= 0: continue 
                except:
                    continue

                data.append({
                    "馬番": len(data) + 1,
                    "馬名": name,
                    "単勝オッズ": win_f,
                    "複勝オッズ_low": place_f
                })
            
            if data:
                return pd.DataFrame(data)
        except Exception as e:
            continue # エラーが起きても次のURLを試す
            
    return pd.DataFrame()


# --- メイン画面レイアウト ---
st.title("🏇 リアルタイム異常オッズ監視ボード")

# サイドバー設定
st.sidebar.header("レース情報入力")
race_id_input = st.sidebar.text_input("Netkeiba Race ID (12桁)", value="202608020211")
st.sidebar.caption("例: 202608020211 (シルクロードS)")

if st.sidebar.button("最新データを取得"):
    with st.spinner('データを解析中...'):
        df = get_real_odds(race_id_input)
        if not df.empty:
            # 異常スコアの計算ロジック
            df['単勝人気'] = df['単勝オッズ'].rank()
            df['複勝人気'] = df['複勝オッズ_low'].rank()
            df['異常スコア'] = df['単勝人気'] - df['複勝人気']
            # グラフサイズ用の補正（マイナス値を防ぐ）
            df['plot_size'] = df['異常スコア'].apply(lambda x: max(x, 1))
            
            st.session_state['df'] = df
            st.success("取得完了！")
        else:
            st.error("データが取得できませんでした。IDが正しいか、または開催中のレースか確認してください。")

# --- 表示セクション ---
if 'df' in st.session_state:
    df = st.session_state['df']
    
    # 指標の表示
    max_anomaly_row = df.loc[df['異常スコア'].idxmax()]
    c1, c2, c3 = st.columns(3)
    c1.metric("分析対象レースID", race_id_input)
    c2.metric("最大乖離馬", max_anomaly_row['馬名'])
    c3.metric("異常スコア", f"{max_anomaly_row['異常スコア']:.1f}")

    st.divider()

    # グラフ表示
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("📊 単複相関分析")
        st.write("左下に浮いている馬ほど、複勝が異常に売れています")
        fig = px.scatter(df, x="単勝オッズ", y="複勝オッズ_low", text="馬名",
                         color="異常スコア", size="plot_size",
                         color_continuous_scale="Reds",
                         labels={"複勝オッズ_low": "複勝オッズ(下限)", "単勝オッズ": "単勝オッズ"})
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.subheader("📈 単勝オッズ断層")
        st.write("棒の高さの急激な変化（断層）に注目")
        st.bar_chart(df.set_index("馬名")["単勝オッズ"])

    # 詳細テーブル
    st.subheader("📋 詳細データ一覧")
    def highlight_row(s):
        return ['background-color: #ffcccc' if v >= 3 else '' for v in s]
    
    st.dataframe(df.style.apply(highlight_row, subset=['異常スコア']).format(precision=1))

else:
    st.info("左のサイドバーにRace IDを入力して「データを取得」ボタンを押してください。")
    st.markdown("""
    ### 💡 使い方
    1. netkeibaなどのURLから12桁のRace IDを見つける。
    2. サイドバーに入力して実行。
    3. **異常スコアが3以上**の馬は、プロの大口投票が入っている可能性があります。
    """)