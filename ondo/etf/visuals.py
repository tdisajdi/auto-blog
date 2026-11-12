"""ETF 시각 자료: 기본 카드·백테스트·손익 캘린더·경쟁/위험/시나리오/섹터 표·거시 온도계.
(2026-11-09 etf_auto.py에서 나눔 - 동작은 그대로)"""
from ondo.etf.data import *  # noqa: F401,F403 - 아래 층의 이름을 그대로 씀
def _add_scenario_analysis(etf_data_cache, title_tickers):
    """실제 연평균성장률(CAGR) 반영 투자 시나리오 분석.
    [중요] 이전에는 d.get('cagr', 0.08)로 기본값 8%를 썼는데, 애초에
    etf_data_cache에 'cagr' 키 자체가 채워지지 않아 사실상 모든 ETF가
    실제 데이터와 무관하게 항상 8%로 시뮬레이션되고 있었음(get_etf_real_data가
    실제로 계산한 5년 총수익률이 다른 변수에만 저장되고 여기로 연결이 안 됨).
    이제 get_etf_real_data가 실제 CAGR을 계산해 넘겨주므로, 그 값이 없을 때만
    (계산 실패 등) 시뮬레이션 자체를 생략하고 그 이유를 명시한다 - 근거 없는
    숫자를 지어내 마치 실제 데이터인 것처럼 보이게 하지 않기 위함."""
    html = '<h3 style="margin-top:30px;">💡 투자 시나리오별 수익/손실 분석</h3>'
    for ticker, d in etf_data_cache.items():
        ticker_clean = ticker.replace(".KS", "").replace(".US", "")
        yield_pct = float(d.get('yield', '0').replace('%', '').split()[0]) if '%' in d.get('yield', '0') else 0.0

        principal = 10_000_000
        annual_return_estimate = d.get('cagr')

        if annual_return_estimate is None:
            html += f"""
<div style="margin-top:20px;padding:15px;background:#fafafa;border:1px solid #e0e0e0;border-radius:6px;">
<p style="margin:0;font-size:13px;color:#7f8c8d;"><em>※ {ticker_clean}은(는) 과거 가격 데이터가 충분하지 않아 장기 보유 시뮬레이션을 계산할 수 없습니다. 최근 수익률 데이터는 위 표를 참고하세요.</em></p>
</div>
"""
            continue

        final_value_5y = principal * ((1 + annual_return_estimate) ** 5)
        annual_dividend = principal * (yield_pct / 100)
        total_5y_dividend = annual_dividend * 5
        overseas = _is_overseas_listed(d)
        div_tax_rate = TAX_US_DIVIDEND_WITHHOLDING if overseas else TAX_DOMESTIC_DIVIDEND
        div_tax_label = "배당세(미국 원천징수 15%)" if overseas else "배당소득세(15.4%)"
        sale_tax_note = ("매도 차익 세금(연 250만 원 공제 후 22%)은 빠져 있습니다." if overseas
                         else "매도 차익 세금(일반계좌 15.4%, 국내 주식형 ETF는 비과세)은 빠져 있습니다.")
        tax_on_dividend = total_5y_dividend * div_tax_rate
        net_after_tax = (final_value_5y - principal) + (total_5y_dividend - tax_on_dividend)

        # [수정] "5년 후 평가액"이 원금보다 늘었는지 줄었는지와 무관하게 항상
        # 빨강으로 고정되어 있었음. CAGR이 음수(예: IBIT처럼 -18%)면 실제로는
        # 원금보다 줄어드는데도 빨강(국내 관행상 상승/이득 신호)으로 표시되어
        # 오해를 줄 수 있었음. 실제 손익 방향에 따라 동적으로 색을 결정.
        value_color = "#c0392b" if final_value_5y >= principal else "#2166ac"
        _y = d.get("cagr_years")   # 11-10: '상장일부터 전체 기간'이라 적혀 있었지만 실제는 최근 5년(없으면 있는 만큼)
        period_txt = "최근 5년 자료" if isinstance(_y, (int, float)) and _y >= 4.9 else (f"상장 이후 약 {_y:.1f}년치 자료" if isinstance(_y, (int, float)) else "확보된 자료 기간")

        html += f"""
<div style="margin-top:20px;padding:15px;background:#fafafa;border:1px solid #e0e0e0;border-radius:6px;">
<p style="margin:0 0 10px 0;font-weight:bold;color:#333;">{ticker_clean} - 실제 데이터 기반 연평균성장률(CAGR {annual_return_estimate*100:.1f}%) 기준: 1,000만원 5년 보유 시뮬레이션</p>
<p style="margin:0 0 10px 0;font-size:12px;color:#888;">※ 이 CAGR은 <strong>{period_txt}</strong>(배당 제외 가격 기준)으로 계산한 값으로, 앞서 본 최근 1년 수익률과는 <strong>기준 기간이 다릅니다</strong>. 과거 수익률을 5년 동안 똑같이 이어 간다고 가정한 계산일 뿐, 앞으로의 수익을 뜻하지 않습니다.</p>
<table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:10px;">
<tr style="background:#f5f5f5;">
<th style="border:1px solid #ddd;padding:10px;text-align:left;">항목</th>
<th style="border:1px solid #ddd;padding:10px;text-align:right;">예상 금액</th>
</tr>
<tr>
<td style="border:1px solid #ddd;padding:10px;">초기 투자</td>
<td style="border:1px solid #ddd;padding:10px;text-align:right;">1,000만원</td>
</tr>
<tr>
<td style="border:1px solid #ddd;padding:10px;">5년 후 유가증권 평가액</td>
<td style="border:1px solid #ddd;padding:10px;text-align:right;"><span style="color:{value_color};">약 {int(final_value_5y/10000):,}만원</span></td>
</tr>
<tr>
<td style="border:1px solid #ddd;padding:10px;">배당금 합계(세전)</td>
<td style="border:1px solid #ddd;padding:10px;text-align:right;">{int(total_5y_dividend/10000):,}만원</td>
</tr>
<tr>
<td style="border:1px solid #ddd;padding:10px;">{div_tax_label}</td>
<td style="border:1px solid #ddd;padding:10px;text-align:right;"><span style="color:#2166ac;">-{int(tax_on_dividend/10000):,}만원</span></td>
</tr>
<tr style="background:#f0f0f0;font-weight:bold;">
<td style="border:1px solid #ddd;padding:10px;">5년 후 총 순수익</td>
<td style="border:1px solid #ddd;padding:10px;text-align:right;"><span style="color:{'#c0392b' if net_after_tax >= 0 else '#2166ac'};font-size:14px;">약 {int(net_after_tax/10000):,}만원</span></td>
</tr>
</table>
<p style="margin-top:10px;font-size:11px;color:#7f8c8d;"><em>※ 위 시나리오는 이 ETF의 실제 과거 가격 데이터로 계산한 연평균성장률(CAGR)을 그대로 5년간 유지된다고 가정한 예시이며, 미래 수익을 보장하지 않습니다. 실제 데이터 확보 기간이 5년 미만인 경우, 확보된 기간의 CAGR을 사용했습니다. 세금은 배당에 대한 것만 반영했고, {sale_tax_note}</em></p>
</div>
"""
    return html


def _add_competitive_comparison(etf_data_cache):
    """비교분석 강화"""
    if len(etf_data_cache) < 2:
        return ""
    
    html = '<h3 style="margin-top:30px;">⚖️ 경쟁 상품 비교: 왜 이 분석 대상인가?</h3>'
    html += '<p style="color:#555;line-height:1.6;">동일 지수 추종 상품들 중 선택 근거:</p>'
    html += '<ul style="padding-left:20px;line-height:1.8;color:#333;">'
    
    for ticker, d in etf_data_cache.items():
        ticker_clean = ticker.replace(".KS", "").replace(".US", "")
        expense = d.get('expense_ratio', 'N/A')
        div_growth = d.get('dividend_growth_rate', 'N/A')
        fx_exposure = d.get('fx_exposure', 'N/A')
        
        html += f'<li><strong>{ticker_clean}</strong>: 보수({expense}), 1년 배당 증가({div_growth}), 환노출({fx_exposure})</li>'
    
    html += '</ul>'
    html += """
<p style="margin-top:15px;padding:12px;background:#fffbea;border-left:3px solid #f39c12;color:#7d6608;font-size:12px;">
<strong>💡 핵심 차별고:</strong> 이 분석이 다른 블로그와 다른 이유는 단순 "어느 ETF 좋다"가 아니라, 
<strong>당신의 구체적 상황(연령, 납입기간, 세금계좌) 기반으로 수익률뿐 아니라 세금·환율·변동성까지</strong> 종합 검토한다는 점입니다.
</p>
"""
    
    return html








def _add_risk_scenarios(etf_data_cache, principal=100_000_000):
    """실제 MDD(최대 낙폭) 기반 위험 시나리오 분석"""
    html = '<h3 style="margin-top:30px;">⚠️ 위기 시나리오: 최악의 경우 내 계좌는?</h3>'
    html += '<p style="color:#555;">각 ETF의 과거 실제 최대 낙폭(MDD)을 기준으로, 1억 원에 적용한 손실 규모입니다.</p>'

    # [수정] 이전에는 <table width:100%>인데 각 셀에 폭 지정이 없어서, ETF가
    # 1~2개뿐일 때 브라우저가 셀 내용물 크기에 맞춰 열을 비정상적으로 좁게
    # 렌더링하는 문제가 있었음(실제 렌더링 확인 결과 글자가 세로로 눌린 듯 보임).
    # 여러 ETF를 나란히 비교하는 경우가 아니면 표보다 카드형이 더 읽기 편해서,
    # ETF가 3개 미만이면 카드형 레이아웃으로 전환한다.
    risk_results_by_ticker = {}
    ticker_count = len(etf_data_cache)

    if ticker_count < 3:
        # 카드형 레이아웃 (1~2개 ETF일 때)
        cards_html = ""
        for ticker, d in etf_data_cache.items():
            ticker_clean = ticker.replace(".KS", "").replace(".US", "")
            mdd_str = str(d.get('mdd', '0')).replace('%', '').strip()
            try:
                mdd_val = float(mdd_str) / 100.0
            except ValueError:
                mdd_val = 0.0
            if mdd_val > 0:
                mdd_val = -mdd_val
            loss_amount = principal * mdd_val
            remaining = principal + loss_amount

            risk_results_by_ticker[ticker] = {
                "principal": principal,
                "mdd_pct": round(mdd_val * 100, 2),
                "loss_amount": round(loss_amount),
                "remaining": round(remaining),
            }

            if mdd_val == 0:
                cards_html += (
                    f'<div style="padding:16px;border:1px solid #ddd;border-radius:8px;margin-bottom:12px;background:#fafafa;">'
                    f'<p style="margin:0;font-weight:bold;color:#333;">{ticker_clean}</p>'
                    f'<p style="margin:8px 0 0;color:#666;">MDD 데이터 없음</p></div>'
                )
            else:
                cards_html += f"""
<div style="padding:18px;border:1px solid #ddd;border-radius:8px;margin-bottom:12px;background:#fafafa;">
<p style="margin:0 0 10px;font-weight:bold;color:#333;font-size:15px;">{ticker_clean}</p>
<div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:12px;">
<div><span style="font-size:12px;color:#5c6575;">실제 최대낙폭(MDD)</span><br/><span style="font-size:17px;font-weight:bold;color:#2166ac;">{mdd_val*100:.2f}%</span></div>
<div><span style="font-size:12px;color:#5c6575;">최대 손실 금액</span><br/><span style="font-size:17px;font-weight:bold;color:#c0392b;">{int(loss_amount/10000):,}만원</span></div>
<div><span style="font-size:12px;color:#5c6575;">잔여 자산</span><br/><span style="font-size:17px;font-weight:bold;color:#555;">{int(remaining/10000):,}만원</span></div>
</div>
</div>
"""
        html += f'<div style="margin-top:20px;padding:15px;border:1px solid #ddd;border-left:4px solid #2166ac;border-radius:4px;background:#fff;">{cards_html}'
    else:
        # 표형 레이아웃 (3개 이상 비교할 때 - 열 최소 너비 지정으로 가독성 확보)
        html += """
<div style="margin-top:20px;padding:15px;border:1px solid #ddd;border-left:4px solid #2166ac;border-radius:4px;background:#fafafa;overflow-x:auto;">
<table style="width:100%;border-collapse:collapse;font-size:13px;">
<tr style="background:#f5f5f5;">
"""
        for ticker in etf_data_cache.keys():
            ticker_clean = ticker.replace(".KS", "").replace(".US", "")
            html += f'<th style="border:1px solid #ddd;padding:10px;min-width:130px;">{ticker_clean}</th>'
        html += '</tr><tr>'

        for ticker, d in etf_data_cache.items():
            mdd_str = str(d.get('mdd', '0')).replace('%', '').strip()
            try:
                mdd_val = float(mdd_str) / 100.0
            except ValueError:
                mdd_val = 0.0
            if mdd_val > 0:
                mdd_val = -mdd_val
            loss_amount = principal * mdd_val
            remaining = principal + loss_amount

            risk_results_by_ticker[ticker] = {
                "principal": principal,
                "mdd_pct": round(mdd_val * 100, 2),
                "loss_amount": round(loss_amount),
                "remaining": round(remaining),
            }

            html += '<td style="border:1px solid #ddd;padding:10px;text-align:center;min-width:130px;">'
            if mdd_val == 0:
                html += '<span style="color:#666;">MDD 데이터 없음</span>'
            else:
                html += f'<span style="color:#2166ac;font-weight:bold;">실제 MDD: {mdd_val*100:.2f}%</span><br/>'
                html += f'<span style="color:#2166ac;font-weight:bold;">최대 손실: {int(loss_amount/10000):,}만원</span><br/>'
                html += f'<span style="color:#666;font-size:11px;">잔액: {int(remaining/10000):,}만원</span>'
            html += '</td>'
        html += '</tr></table></div>'

    html += """
<p style="font-size:11px;color:#555;margin-top:10px;line-height:1.5;">
※ 가정이 아니라 해당 ETF의 최근 5년 실제 최대 낙폭(MDD)을 1억 원에 적용한 값입니다. 과거 낙폭이 앞으로의 최대 손실을 뜻하지는 않습니다.
</p>
"""
    if ticker_count < 3:
        html += "</div>"
    return html, risk_results_by_ticker








def _add_sector_deep_analysis(etf_data_cache, macro_data):
    """심화 섹터 분석 (팩트 기반)"""
    html = '<h3 style="margin-top:30px;">🔍 섹터 분석 및 거시경제 전망</h3>'
    primary_etf = list(etf_data_cache.values())[0]
    ticker = primary_etf.get('ticker', list(etf_data_cache.keys())[0]).replace(".KS", "").replace(".US", "")
    real_sector = primary_etf.get('sector', '종합 / 판단 불가')
    real_industry = primary_etf.get('industry', '종합 / 판단 불가')
    
    usd_krw = float(str(macro_data.get('usd_krw', '1300원')).replace('원', '').replace(',', ''))
    
    # 11-11: '거시경제 연계 대응 전략 - 전망: 긍정적/보수적 접근 필요'는 환율·금리로 만든 전망(투자 판단)이고, '국채 금리는 밸류에이션에
    # 영향' 같은 일반론을 작가가 따라 씀(재개 시험 ② VOO) → 사실만: 투자 영역 + 환노출 여부. 10년물 금리는 금리 글에만(11-10).
    html += f'''
<p style="color:#555;">{ticker} ETF의 투자 영역: <strong>{real_sector} / {real_industry}</strong></p>
<div style="margin:20px 0;padding:15px;border:1px solid #e9ecef;border-radius:8px;background:#f8f9fa;">
<h4 style="margin:0 0 10px 0;color:#333;">🌍 환율 노출</h4>
<p style="margin:0;font-size:13px;">현재 원/달러 환율 <strong>{usd_krw:,.0f}원</strong>. 달러로 거래되는 해외 상장 ETF(환노출)는 환율 변화가 원화로 본 수익률에 그대로 반영됩니다.</p>
</div>
'''

    # 스크래핑한 실제 Top 5 표 삽입 (데이터가 있을 때만 노출)
    top_holdings = primary_etf.get('top_holdings', [])
    if top_holdings:
        html += '<h4 style="margin:25px 0 10px 0; font-size:15px; color:#212529;">📦 상위 5대 보유 종목 (Top 5 Holdings)</h4>'
        html += '<div style="margin:10px 0; overflow-x:auto;">'
        html += '<table style="width:100%; border-collapse:collapse; font-size:13px; text-align:left; border:1px solid #dee2e6;">'
        html += '<tr style="background:#f1f3f5; border-bottom:2px solid #dee2e6;">'
        html += '<th style="padding:10px; border-right:1px solid #dee2e6; text-align:center;">순위</th>'
        html += '<th style="padding:10px; border-right:1px solid #dee2e6;">종목명 (티커)</th>'
        html += '<th style="padding:10px; text-align:right;">비중</th>'
        html += '</tr>'
        
        for i, holding in enumerate(top_holdings[:5], 1):
            symbol = holding.get("symbol", "")
            name = holding.get("name", "")
            weight = holding.get("weight", 0)
            
            html += '<tr style="border-bottom:1px solid #e9ecef;">'
            html += f'<td style="padding:10px; border-right:1px solid #e9ecef; text-align:center; color:#868e96;">{i}</td>'
            html += f'<td style="padding:10px; border-right:1px solid #e9ecef;"><strong>{name}</strong> <span style="color:#666; font-size:11px;">({symbol})</span></td>'
            html += f'<td style="padding:10px; text-align:right; font-weight:bold; color:#1f3c88;">{weight:.2f}%</td>'
            html += '</tr>'
            
        html += '</table></div><br>'
    
    div_stability = primary_etf.get('dividend_stability_desc', '')
    if div_stability: html += f'<div style="margin:15px 0;padding:10px;background:#e8f5e8;border-left:4px solid #28a745;border-radius:4px;"><strong>💰 배당 안정성:</strong> {div_stability}</div>'
    
    ma200_info = primary_etf.get('ma200_info')
    if ma200_info:
        diff_pct = ma200_info.get('diff_pct', 0)
        color = '#c0392b' if diff_pct > 0 else '#2166ac'
        ma200_status = ma200_info.get('status', '')
        html += f'<div style="margin:15px 0;padding:10px;background:#e3f2fd;border-left:4px solid #4A90E2;border-radius:4px;"><strong>📈 기술 분석 (MA200):</strong> {ma200_status} (현재가 MA200 대비 <span style="color:{color};font-weight:bold;">{diff_pct:+.2f}%</span>)</div>'
    
    html += _build_advanced_sections(etf_data_cache)
    return html














def _create_backtest_simulation_chart(ticker, data, wrapper_style, usd_krw_rate=1300.0, investment_amount=10000000):
    """
    [신규] 기존에는 Portfolio Visualizer 외부 사이트를 셀레니움으로 조작해 스크린샷을
    찍으려 했으나, 사이트 UI가 바뀌면서 계속 깨지는 문제가 있었고(엉뚱한 샘플 포트폴리오
    화면이 찍힘), 애초에 본문에 자동 삽입되지도 않는 죽은 기능이었음.

    외부 사이트 의존성을 완전히 없애고, 이미 갖고 있는 가격 데이터(yfinance)로 직접
    "거치식(목돈을 한 번에 투자)" vs "적립식(매달 나눠서 투자, DCA)" 시뮬레이션 곡선을
    그려서 대체함. 월봉/주봉처럼 같은 데이터를 촘촘하게만 보여주는 것보다, 실제로
    결과가 달라지는 두 투자 방식을 비교하는 것이 독자에게 더 실질적인 정보를 줌.
    """
    is_kr = ticker.endswith('.KS')
    raw_code = ticker.replace('.KS', '') if is_kr else ticker
    safe_id = raw_code.replace('.', '_')

    try:
        ticker_obj = yf.Ticker(f"{raw_code}.KS" if is_kr else ticker)
        hist = ticker_obj.history(period="5y")

        if not hist.empty:
            hist['Close'] = pd.to_numeric(hist['Close'], errors='coerce')
            hist = hist.dropna(subset=['Close'])
            if len(hist) > 21:
                hist = hist.iloc[:-21]

        if hist.empty or len(hist) < 30:
            return "", None  # 데이터 부족 시 조용히 생략 (필수 요소가 아니므로 fallback 링크까지는 불필요)

        currency_symbol = "₩" if is_kr else "$"
        close = hist['Close'].copy()
        if not is_kr and usd_krw_rate > 1.0:
            close = close * usd_krw_rate
            currency_symbol = "₩"

        # 월말 종가로 리샘플링 (일별로 하면 데이터 포인트가 너무 많아 무거워짐)
        monthly_close = close.resample('ME').last().dropna()
        if len(monthly_close) < 6:
            return "", None

        dates_str = monthly_close.index.strftime('%Y-%m').tolist()
        prices = monthly_close.tolist()

        # --- 시나리오 1: 거치식 (첫 달에 investment_amount 전액 투자) ---
        shares_lump = investment_amount / prices[0]
        lump_values = [round(shares_lump * p) for p in prices]

        # --- 시나리오 2: 적립식 DCA (전체 기간에 걸쳐 매달 동일 금액 분할 투자) ---
        monthly_invest = investment_amount / len(prices)
        dca_shares = 0.0
        dca_values = []
        for p in prices:
            dca_shares += monthly_invest / p
            dca_values.append(round(dca_shares * p))

        chart_title = data.get("name", ticker)
        full_title = f"{chart_title}" if is_kr else f"{chart_title} ({ticker})"

        chart_id = f"backtest_chart_{safe_id}"
        plotly_script_id = f"backtest_plotly_script_{safe_id}"
        btn_lump_id = f"btn_lump_{safe_id}"
        btn_dca_id = f"btn_dca_{safe_id}"

        chart_data = [
            {
                'type': 'scatter', 'mode': 'lines', 'x': dates_str, 'y': lump_values,
                'name': '거치식 (한 번에 투자)', 'visible': True,
                'line': {'color': '#1f3c88', 'width': 3},
            },
            {
                'type': 'scatter', 'mode': 'lines', 'x': dates_str, 'y': dca_values,
                'name': '적립식 (매달 분할 투자)', 'visible': False,
                'line': {'color': '#e67e22', 'width': 3},
            },
        ]

        amount_str = f"{investment_amount:,.0f}"
        chart_layout = {
            'title': f"{full_title} - {amount_str}{currency_symbol} 거치식 시뮬레이션",
            'yaxis': {'title': f"평가금액 ({currency_symbol})"},
            'xaxis': {'title': '투자 개월', 'type': 'category', 'nticks': 8, 'tickangle': 0},
            'template': 'plotly_white',
            'hovermode': 'x unified',
            'height': 420,
            'margin': {'t': 60, 'b': 45, 'l': 60, 'r': 20},
        }

        chart_js = (
            f'<script>'
            f'(function(){{'
            f'  function initPlotly_{safe_id}() {{'
            f'    var gd = document.getElementById("{chart_id}");'
            f'    if(!gd) return;'
            f'    var data = {json.dumps(chart_data, ensure_ascii=False)};'
            f'    var layout = {json.dumps(chart_layout, ensure_ascii=False)};'
            f'    var config = {{responsive: true, displaylogo: false}};'
            f'    Plotly.newPlot(gd, data, layout, config);'
            f'    var btn_lump = document.getElementById("{btn_lump_id}");'
            f'    var btn_dca = document.getElementById("{btn_dca_id}");'
            f'    if(btn_lump) btn_lump.addEventListener("click", function(){{ Plotly.restyle(gd, {{"visible": [true, false]}}); Plotly.relayout(gd, {{"title.text": "{full_title} - {amount_str}{currency_symbol} 거치식 시뮬레이션"}}); }});'
            f'    if(btn_dca) btn_dca.addEventListener("click", function(){{ Plotly.restyle(gd, {{"visible": [false, true]}}); Plotly.relayout(gd, {{"title.text": "{full_title} - 월 {round(investment_amount/len(prices)):,}{currency_symbol} 적립식 시뮬레이션"}}); }});'
            f'  }}'
            f'  if(window.Plotly) initPlotly_{safe_id}();'
            f'  else if(!document.getElementById("{plotly_script_id}")) {{'
            f'    var s = document.createElement("script");'
            f'    s.id = "{plotly_script_id}";'
            f'    s.src = "https://cdn.plot.ly/plotly-2.34.0.min.js";'
            f'    s.onload = initPlotly_{safe_id};'
            f'    document.head.appendChild(s);'
            f'  }} else {{'
            f'    document.getElementById("{plotly_script_id}").addEventListener("load", initPlotly_{safe_id});'
            f'  }}'
            f'}})();'
            f'</script>'
        )

        backtest_aria_label = f"{full_title} 거치식 vs 적립식 투자 시뮬레이션 그래프, {amount_str}{currency_symbol} 기준"

        # [신규] 연령별 포트폴리오 가이드 등 다른 섹션에서 "이 ETF만의 실제 숫자"를
        # 재사용할 수 있도록, 계산 중간값을 버리지 않고 딕셔너리로 함께 반환한다.
        # (CHART_MODE와 무관하게 항상 동일하게 계산됨)
        lump_final = lump_values[-1]
        dca_final = dca_values[-1]
        backtest_result = {
            "ticker": ticker,
            "currency_symbol": currency_symbol,
            "investment_amount": investment_amount,
            "lump_final_value": lump_final,
            "lump_return_pct": round((lump_final - investment_amount) / investment_amount * 100, 2),
            "dca_final_value": dca_final,
            "dca_return_pct": round((dca_final - investment_amount) / investment_amount * 100, 2),
            "months": len(prices),
        }

        if CHART_MODE == "image":
            # [신규] "버튼으로 전환"하는 인터랙션은 이미지로 구현 불가능하므로,
            # 거치식/적립식 각각을 정적 PNG로 렌더링해 <details>(순수 HTML)로
            # 감싸 접어두고 클릭하면 펼쳐보는 방식으로 대체한다.
            lump_layout = dict(chart_layout)
            lump_layout['title'] = f"{full_title} - {amount_str}{currency_symbol} 거치식 시뮬레이션"
            lump_data = [{**chart_data[0], 'visible': True}]
            lump_img = _plotly_fig_to_img_tag(lump_data, lump_layout, f"{full_title} 거치식 투자 시뮬레이션", width=700, height=420)

            dca_layout = dict(chart_layout)
            dca_layout['title'] = f"{full_title} - 월 {round(investment_amount/len(prices)):,}{currency_symbol} 적립식 시뮬레이션"
            dca_data = [{**chart_data[1], 'visible': True}]
            dca_img = _plotly_fig_to_img_tag(dca_data, dca_layout, f"{full_title} 적립식 투자 시뮬레이션", width=700, height=420)

            if not lump_img and not dca_img:
                return "", backtest_result  # 이미지 실패해도 계산값은 다른 섹션이 쓸 수 있게 반환

            caption = (
                f'<p style="font-size:12px;color:#888;margin-top:8px;text-align:center;">'
                f'※ 최근 5년 실제 가격 데이터를 기반으로, {amount_str}{currency_symbol}을 처음에 한 번에 투자(거치식)했을 때와 '
                f'매달 나누어 투자(적립식)했을 때의 평가금액 변화를 비교한 시뮬레이션입니다. 배당 재투자, 세금, 환율 변동은 반영되지 않았습니다.'
                f'</p>'
            )

            sections_html = ""
            if lump_img:
                sections_html += f'''
<details open style="margin-bottom:10px;border:1px solid #e0e0e0;border-radius:8px;padding:14px;">
<summary style="cursor:pointer;font-weight:bold;color:#1f3c88;list-style:none;">💰 거치식(한 번에 투자) 시뮬레이션 보기 (클릭)</summary>
<div style="margin-top:15px;">{lump_img}</div>
</details>
'''
            if dca_img:
                sections_html += f'''
<details style="margin-bottom:10px;border:1px solid #e0e0e0;border-radius:8px;padding:14px;">
<summary style="cursor:pointer;font-weight:bold;color:#e67e22;list-style:none;">💰 적립식(매달 분할 투자) 시뮬레이션 보기 (클릭)</summary>
<div style="margin-top:15px;">{dca_img}</div>
</details>
'''
            safe_wrapper_style_img = wrapper_style + " overflow: visible !important;"
            html_output = f'<div style="{safe_wrapper_style_img}"><h4 style="margin-bottom:10px;">📊 {full_title} 투자 시뮬레이션: 거치식 vs 적립식</h4>{sections_html}{caption}</div>'
            return html_output, backtest_result

        chart_div = f'<div id="{chart_id}" role="img" aria-label="{backtest_aria_label}" style="width:100%;min-height:420px;"></div>'
        button_html = (
            f'<div style="display:flex; justify-content:center; flex-wrap:wrap; gap:8px; margin-top:5px; margin-bottom:15px;">'
            f'<button id="{btn_lump_id}" type="button" style="padding:8px 14px; border:1px solid #1f3c88; background:#fff; color:#1f3c88; cursor:pointer; border-radius:6px; font-weight:bold;">거치식</button>'
            f'<button id="{btn_dca_id}" type="button" style="padding:8px 14px; border:1px solid #e67e22; background:#fff; color:#e67e22; cursor:pointer; border-radius:6px; font-weight:bold;">적립식(DCA)</button>'
            f'</div>'
        )
        caption = (
            f'<p style="font-size:12px;color:#888;margin-top:8px;text-align:center;">'
            f'※ 최근 5년 실제 가격 데이터를 기반으로, {amount_str}{currency_symbol}을 처음에 한 번에 투자(거치식)했을 때와 '
            f'매달 나누어 투자(적립식)했을 때의 평가금액 변화를 비교한 시뮬레이션입니다. 배당 재투자, 세금, 환율 변동은 반영되지 않았습니다.'
            f'</p>'
        )

        safe_wrapper_style = wrapper_style + " overflow: visible !important;"
        html_output = f'<div style="{safe_wrapper_style}"><h4 style="margin-bottom:10px;">📊 {full_title} 투자 시뮬레이션: 거치식 vs 적립식</h4>{chart_div}{button_html}{chart_js}{caption}</div>'

        return html_output, backtest_result

    except Exception as e:
        print(f"⚠️ {ticker} 백테스트 시뮬레이션 차트 생성 실패: {type(e).__name__}: {e}")
        return "", None  # 실패해도 본문 전체를 막지 않도록 조용히 생략






def _create_widget_html(ticker, data, wrapper_style, usd_krw_rate=1300.0):
    """티스토리 환경에 최적화된 JS 인터랙티브 차트 (렌지슬라이더 제거, 날짜 정렬, 버튼 보안 우회)"""
    is_kr = ticker.endswith('.KS')
    raw_code = ticker.replace('.KS', '') if is_kr else ticker
    safe_id = raw_code.replace('.', '_')

    try:
        ticker_obj = yf.Ticker(f"{raw_code}.KS" if is_kr else ticker)
        hist = ticker_obj.history(period="5y") 
        
        if not hist.empty:
            hist[['Open', 'High', 'Low', 'Close']] = hist[['Open', 'High', 'Low', 'Close']].apply(pd.to_numeric, errors='coerce')
            hist = hist.dropna(subset=['Open', 'High', 'Low', 'Close'])
            if len(hist) > 21: hist = hist.iloc[:-21]
        
        if hist.empty:
            return f'<div style="{wrapper_style}"><p>📊 차트 데이터가 없습니다.</p></div>'
            
        currency_symbol = "₩" if is_kr else "$"
        if not is_kr and usd_krw_rate > 1.0:
            hist[['Open', 'High', 'Low', 'Close']] *= usd_krw_rate
            currency_symbol = "₩"
            
        monthly = hist.resample('ME').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()
        weekly = hist.resample('W').agg({'Open':'first', 'High':'max', 'Low':'min', 'Close':'last'}).dropna()

        if monthly.empty or weekly.empty:
            return f'<div style="{wrapper_style}"><p>📊 데이터가 부족합니다.</p></div>'

        # 문자열 리스트로 추출
        monthly_idx_str = monthly.index.strftime('%Y-%m-%d').tolist()
        weekly_idx_str = weekly.index.strftime('%Y-%m-%d').tolist()
        
        chart_title = data.get("name", ticker)
        full_title = f"{chart_title}" if is_kr else f"{chart_title} ({ticker})"
        
        chart_id = f"chart_{safe_id}"
        plotly_script_id = f"plotly_script_{safe_id}"
        btn_m_id = f"btn_m_{safe_id}"
        btn_w_id = f"btn_w_{safe_id}"

        # 1. JS 데이터 구성
        chart_data = [
            {
                'type': 'candlestick',
                'x': monthly_idx_str,
                'open': monthly['Open'].tolist(),
                'high': monthly['High'].tolist(),
                'low': monthly['Low'].tolist(),
                'close': monthly['Close'].tolist(),
                'name': '월봉',
                'visible': True
            },
            {
                'type': 'candlestick',
                'x': weekly_idx_str,
                'open': weekly['Open'].tolist(),
                'high': weekly['High'].tolist(),
                'low': weekly['Low'].tolist(),
                'close': weekly['Close'].tolist(),
                'name': '주봉',
                'visible': False
            }
        ]

        # 2. JS 레이아웃 구성 (정신없는 UI 수정)
        chart_layout = {
            'title': f"{full_title} - 월봉",
            'yaxis': {'title': f"가격 ({currency_symbol})"},
            'xaxis': {
                'title': '날짜', 
                'type': 'category', 
                'rangeslider': {'visible': False}, # 🚨 렌지 슬라이더 강제 제거
                'nticks': 8,                       # 🚨 틱(날짜) 개수를 8개로 줄여서 여백 확보
                'tickangle': 0                     # 🚨 세로로 눕는 현상을 막고 가로 텍스트로 고정
            },
            'template': 'plotly_white',
            'hovermode': 'x unified',
            'height': 450, 
            'margin': {'t': 60, 'b': 45, 'l': 50, 'r': 20}
        }

        # 3. 티스토리 보안 우회를 위한 Script 바인딩
        chart_js = (
            f'<script>'
            f'(function(){{'
            f'  function initPlotly_{safe_id}() {{'
            f'    var gd = document.getElementById("{chart_id}");'
            f'    if(!gd) return;'
            f'    var data = {json.dumps(chart_data, ensure_ascii=False)};'
            f'    var layout = {json.dumps(chart_layout, ensure_ascii=False)};'
            f'    var config = {{responsive: true, displaylogo: false}};'
            f'    Plotly.newPlot(gd, data, layout, config);'
            f'    var btn_m = document.getElementById("{btn_m_id}");'
            f'    var btn_w = document.getElementById("{btn_w_id}");'
            f'    if(btn_m) btn_m.addEventListener("click", function(){{ Plotly.restyle(gd, {{"visible": [true, false]}}); Plotly.relayout(gd, {{"title.text": "{full_title} - 월봉"}}); }});'
            f'    if(btn_w) btn_w.addEventListener("click", function(){{ Plotly.restyle(gd, {{"visible": [false, true]}}); Plotly.relayout(gd, {{"title.text": "{full_title} - 주봉"}}); }});'
            f'  }}'
            f'  if(window.Plotly) initPlotly_{safe_id}();'
            f'  else if(!document.getElementById("{plotly_script_id}")) {{'
            f'    var s = document.createElement("script");'
            f'    s.id = "{plotly_script_id}";'
            f'    s.src = "https://cdn.plot.ly/plotly-2.34.0.min.js";'
            f'    s.onload = initPlotly_{safe_id};'
            f'    document.head.appendChild(s);'
            f'  }} else {{'
            f'    document.getElementById("{plotly_script_id}").addEventListener("load", initPlotly_{safe_id});'
            f'  }}'
            f'}})();'
            f'</script>'
        )

        chart_aria_label = f"{full_title} 월봉 및 주봉 캔들스틱 차트, 5년치 가격 추이"

        if CHART_MODE == "image":
            # [신규] <script> 태그가 실행되지 않는 환경(무료 워드프레스 등)을
            # 위해, 월봉/주봉을 각각 정적 PNG 이미지로 렌더링한다. "버튼으로
            # 전환"하는 인터랙션은 이미지로는 구현 불가능하므로, 대신 각각을
            # <details>(순수 HTML, JS 불필요)로 감싸 접어두고 클릭하면
            # 펼쳐서 보는 방식으로 대체한다.
            monthly_layout = dict(chart_layout)
            monthly_layout['title'] = f"{full_title} - 월봉"
            monthly_data = [{**chart_data[0], 'visible': True}]
            monthly_img = _plotly_fig_to_img_tag(monthly_data, monthly_layout, f"{full_title} 월봉 캔들스틱 차트", width=700, height=450)

            weekly_layout = dict(chart_layout)
            weekly_layout['title'] = f"{full_title} - 주봉"
            weekly_data = [{**chart_data[1], 'visible': True}]
            weekly_img = _plotly_fig_to_img_tag(weekly_data, weekly_layout, f"{full_title} 주봉 캔들스틱 차트", width=700, height=450)

            if not monthly_img and not weekly_img:
                return ""  # 둘 다 실패하면 이 섹션 자체를 조용히 생략

            sections_html = ""
            if monthly_img:
                sections_html += f'''
<details open style="margin-bottom:10px;border:1px solid #e0e0e0;border-radius:8px;padding:14px;">
<summary style="cursor:pointer;font-weight:bold;color:#1f3c88;list-style:none;">📈 {full_title} 월봉 차트 보기 (클릭)</summary>
<div style="margin-top:15px;">{monthly_img}</div>
</details>
'''
            if weekly_img:
                sections_html += f'''
<details style="margin-bottom:10px;border:1px solid #e0e0e0;border-radius:8px;padding:14px;">
<summary style="cursor:pointer;font-weight:bold;color:#1f3c88;list-style:none;">📈 {full_title} 주봉 차트 보기 (클릭)</summary>
<div style="margin-top:15px;">{weekly_img}</div>
</details>
'''
            return f'<div style="{wrapper_style}">{sections_html}</div>'

        chart_div = f'<div id="{chart_id}" role="img" aria-label="{chart_aria_label}" style="width:100%;min-height:450px;"></div>'
        button_html = (
            f'<div style="display:flex; justify-content:center; flex-wrap:wrap; gap:8px; margin-top:5px; margin-bottom:15px;">'
            f'<button id="{btn_m_id}" type="button" style="padding:8px 14px; border:1px solid #4A90E2; background:#fff; color:#1f3c88; cursor:pointer; border-radius:6px; font-weight:bold;">월봉</button>'
            f'<button id="{btn_w_id}" type="button" style="padding:8px 14px; border:1px solid #4A90E2; background:#fff; color:#1f3c88; cursor:pointer; border-radius:6px; font-weight:bold;">주봉</button>'
            f'</div>'
        )

        safe_wrapper_style = wrapper_style + " overflow: visible !important;"
        return f'<div style="{safe_wrapper_style}">{chart_div}{button_html}{chart_js}</div>'
        
    except Exception as e:
        print(f"⚠️ {ticker} Plotly 차트 생성 실패: {type(e).__name__}: {e}")
        fallback_url = f"https://finance.naver.com/item/main.naver?code={raw_code}" if is_kr else f"https://finance.yahoo.com/quote/{ticker}"
        fallback_name = "네이버 금융" if is_kr else "Yahoo Finance"
        return (
            f'<div style="{wrapper_style} text-align: center; padding: 30px; background: #f9f9f9; border-radius: 8px;">'
            f'<h4 style="color: #333; margin-bottom: 15px;">📊 {data.get("name", ticker)}</h4>'
            f'<p style="color: #666; margin-bottom: 20px;">차트 데이터를 생성할 수 없습니다. 아래 링크에서 확인하세요.</p>'
            f'<a href="{fallback_url}" target="_blank" style="display: inline-block; background: #2ecc71; color: white; padding: 10px 20px; border-radius: 5px; text-decoration: none; font-weight: bold;">📈 {fallback_name}에서 보기</a>'
            f'</div>'
        )

def _plotly_fig_to_img_tag(chart_data, chart_layout, alt_text, width=700, height=400):
    """[신규] Plotly 차트 데이터를 정적 PNG 이미지로 렌더링해 <img> 태그로
    반환한다. CHART_MODE=image일 때 사용되며, <script> 태그 없이 순수 HTML
    <img>만으로 차트를 보여줄 수 있어 무료 워드프레스 요금제에서도 작동한다.

    이미지는 파일로 저장해 별도 업로드하는 대신 base64로 인코딩해 <img
    src="data:image/png;base64,...">로 직접 HTML에 심는다 - 이러면 이미지
    업로드라는 별도 반자동 단계 없이, 완성된 HTML 하나만 붙여넣으면 된다.

    실패 시(kaleido 미설치, Chrome 없음 등) 빈 문자열을 반환하고 원인을
    로그로 남긴다 - 이 경우 호출부가 안전하게 이 섹션을 생략해야 한다."""
    try:
        import plotly.graph_objects as go
        import base64

        fig = go.Figure(data=chart_data, layout=chart_layout)
        img_bytes = fig.to_image(format="png", width=width, height=height, scale=2)
        b64_data = base64.b64encode(img_bytes).decode('utf-8')
        return f'<img src="data:image/png;base64,{b64_data}" alt="{alt_text}" style="width:100%;max-width:{width}px;height:auto;display:block;margin:0 auto;" />'
    except ImportError:
        print("⚠️ 이미지 차트 생성 실패: plotly 또는 kaleido가 설치되지 않았습니다. (pip install plotly kaleido)")
        return ""
    except Exception as e:
        print(f"⚠️ 이미지 차트 생성 실패: {type(e).__name__}: {e}")
        print("   Chrome이 설치되어 있는지 확인해보세요 (kaleido 1.0+는 Chrome이 필요합니다).")
        return ""


def _create_return_calendar_heatmap(ticker, data, wrapper_style, usd_krw_rate=1300.0, months=3):
    """[신규] '존버 캘린더' - 최근 N개월 일별 수익률을 깃허브 잔디밭 스타일 히트맵으로 시각화.
    - 예측이 아니라 100% 확정된 과거 종가 기반 계산이라 정보 왜곡/오류 위험이 낮음.
    - 한국 증시 관행에 맞춰 상승(+)=빨강, 하락(-)=파랑으로 색상 지정
      (기존 코드가 미국식 초록/빨강 관행을 쓰고 있던 것과는 별개로, 이 위젯은
      처음부터 한국 독자에게 익숙한 배색으로 만듦).
    - <details>/<summary>로 기본은 접힌 상태 - 본문이 어수선해지지 않도록 함.
    """
    is_kr = ticker.endswith(".KS")
    raw_code = ticker.replace(".KS", "") if is_kr else ticker
    safe_id = raw_code.replace(".", "_")

    try:
        ticker_obj = yf.Ticker(f"{raw_code}.KS" if is_kr else ticker)
        # 주말/공휴일을 감안해 여유 있게 가져온 뒤 최근 N개월만 자름
        hist = ticker_obj.history(period="9mo")
        if hist.empty:
            return ""

        hist = hist.copy()
        hist['Close'] = pd.to_numeric(hist['Close'], errors='coerce')
        hist = hist.dropna(subset=['Close'])

        cutoff = hist.index.max() - pd.DateOffset(months=months)
        hist = hist[hist.index >= cutoff]
        if len(hist) < 5:
            return ""

        daily_ret = hist['Close'].pct_change().dropna() * 100
        if daily_ret.empty:
            return ""

        # 요일(월~금)을 y축, ISO 주차를 x축으로 배치해 달력형 격자를 구성
        weekday_labels = ['월', '화', '수', '목', '금']
        iso = daily_ret.index.isocalendar()
        week_keys = [f"{y}-W{w:02d}" for y, w in zip(iso['year'], iso['week'])]
        unique_weeks = sorted(set(week_keys), key=lambda s: (int(s[:4]), int(s[6:])))

        z = [[None] * len(unique_weeks) for _ in range(5)]
        hover = [[""] * len(unique_weeks) for _ in range(5)]
        week_index = {w: i for i, w in enumerate(unique_weeks)}

        for date, ret, wk in zip(daily_ret.index, daily_ret.values, week_keys):
            weekday = date.weekday()  # 0=월 ... 4=금
            if weekday > 4:
                continue
            col = week_index[wk]
            z[weekday][col] = round(float(ret), 2)
            sign = "+" if ret >= 0 else ""
            hover[weekday][col] = f"{date.strftime('%Y-%m-%d')}<br>{sign}{ret:.2f}%"

        max_abs = max((abs(v) for row in z for v in row if v is not None), default=1.0) or 1.0

        # 한국 증시 관행: 상승(+)=빨강, 하락(-)=파랑
        colorscale = [
            [0.0, "#2166ac"],   # 최대 하락 - 진한 파랑
            [0.5, "#f7f7f7"],   # 보합(0%) - 회색
            [1.0, "#b2182b"],   # 최대 상승 - 진한 빨강
        ]

        chart_id = f"calendar_{safe_id}"
        plotly_script_id = f"calendar_plotly_script_{safe_id}"
        chart_name = data.get("name", ticker)

        chart_data = [{
            "type": "heatmap",
            "z": z,
            "x": unique_weeks,
            "y": weekday_labels,
            "text": hover,
            "hoverinfo": "text",
            "zmin": -max_abs,
            "zmax": max_abs,
            "colorscale": colorscale,
            "showscale": True,
            "xgap": 3,
            "ygap": 3,
            "colorbar": {"title": "%", "thickness": 12},
        }]
        chart_layout = {
            "title": f"{chart_name} 최근 {months}개월 일별 손익 캘린더",
            "xaxis": {"title": "", "type": "category", "tickangle": -45, "nticks": 10},
            "yaxis": {"title": "", "autorange": "reversed"},
            "template": "plotly_white",
            "height": 300,
            "margin": {"t": 50, "b": 60, "l": 40, "r": 20},
        }

        chart_js = (
            f'<script>'
            f'(function(){{'
            f'  function initCalendar_{safe_id}() {{'
            f'    var gd = document.getElementById("{chart_id}");'
            f'    if(!gd) return;'
            f'    var data = {json.dumps(chart_data, ensure_ascii=False)};'
            f'    var layout = {json.dumps(chart_layout, ensure_ascii=False)};'
            f'    var config = {{responsive: true, displaylogo: false}};'
            f'    Plotly.newPlot(gd, data, layout, config);'
            f'  }}'
            f'  var trigger = document.getElementById("details_{chart_id}");'
            f'  var rendered_{safe_id} = false;'
            f'  function renderOnce_{safe_id}() {{'
            f'    if(rendered_{safe_id}) return;'
            f'    rendered_{safe_id} = true;'
            f'    if(window.Plotly) initCalendar_{safe_id}();'
            f'    else if(!document.getElementById("{plotly_script_id}")) {{'
            f'      var s = document.createElement("script");'
            f'      s.id = "{plotly_script_id}";'
            f'      s.src = "https://cdn.plot.ly/plotly-2.34.0.min.js";'
            f'      s.onload = initCalendar_{safe_id};'
            f'      document.head.appendChild(s);'
            f'    }} else {{'
            f'      document.getElementById("{plotly_script_id}").addEventListener("load", initCalendar_{safe_id});'
            f'    }}'
            f'  }}'
            # <details>가 펼쳐질 때만 렌더링 - 접힌 상태에서 불필요하게 차트를 그리지 않음
            f'  if(trigger) trigger.addEventListener("toggle", function(){{ if(trigger.open) renderOnce_{safe_id}(); }});'
            f'}})();'
            f'</script>'
        )

        aria_label = f"{chart_name} 최근 {months}개월 일별 수익률 달력형 히트맵"

        if CHART_MODE == "image":
            # [신규] <script> 태그가 실행되지 않는 환경(무료 워드프레스 등)을
            # 위해, 정적 PNG 이미지로 렌더링해 <img> 태그로 보여준다.
            # <details> 접기/펼치기는 포기하고 항상 펼쳐진 상태로 보여준다
            # (JS 없이는 toggle 이벤트를 걸 수 없으므로).
            img_tag = _plotly_fig_to_img_tag(chart_data, chart_layout, aria_label, width=700, height=300)
            if not img_tag:
                return ""  # 이미지 생성 실패 시 이 섹션 자체를 조용히 생략
            return f'''
<div style="{wrapper_style}margin-top:20px;border:1px solid #e0e0e0;border-radius:8px;padding:14px;">
<p style="margin:0 0 12px 0;font-weight:bold;color:#1f3c88;">📅 {chart_name} 최근 {months}개월 손익 캘린더</p>
{img_tag}
<p style="font-size:11px;color:#888;margin-top:8px;text-align:center;">
※ 실제 과거 종가 기준 일별 등락률입니다(예측 아님). 빨강=상승, 파랑=하락 (국내 증시 표기 관행).
</p>
</div>
'''

        chart_div = f'<div id="{chart_id}" role="img" aria-label="{aria_label}" style="width:100%;min-height:300px;"></div>'

        return f'''
<details id="details_{chart_id}" style="{wrapper_style}margin-top:20px;border:1px solid #e0e0e0;border-radius:8px;padding:14px;">
<summary style="cursor:pointer;font-weight:bold;color:#1f3c88;list-style:none;">📅 {chart_name} 최근 {months}개월 손익 캘린더 보기 (클릭)</summary>
<div style="margin-top:15px;">
{chart_div}
{chart_js}
<p style="font-size:11px;color:#888;margin-top:8px;text-align:center;">
※ 실제 과거 종가 기준 일별 등락률입니다(예측 아님). 빨강=상승, 파랑=하락 (국내 증시 표기 관행).
</p>
</div>
</details>
'''
    except Exception as e:
        print(f"⚠️ {ticker} 손익 캘린더 생성 실패: {type(e).__name__}: {e}")
        return ""


def _build_macro_thermometers_chart(indicators):
    """
    [신규] 변동성/밸류에이션/환율/인플레이션 4개 온도계 + 가중평균(30/30/20/20)
    종합 온도계를 Plotly 'indicator'(gauge+number) 트레이스로 그린다.

    기존 CHART_MODE 분기를 그대로 재사용한다:
    - CHART_MODE=script: 인터랙티브 Plotly (백테스트/캔들 차트와 동일한 패턴)
    - CHART_MODE=image: kaleido로 렌더링한 정적 PNG (_plotly_fig_to_img_tag 재사용)

    누락된 지표는 조용히 빼고 있는 지표만으로 종합 온도를 계산한다(가중치 정규화).
    지표가 하나도 없으면 빈 문자열을 반환해 섹션 자체를 생략한다(필수 요소 아님).
    """
    labels = {
        'volatility': '변동성',
        'valuation': '밸류에이션',
        'fx': '환율',
        'inflation': '인플레이션',
    }
    weights = {'volatility': 0.3, 'valuation': 0.3, 'fx': 0.2, 'inflation': 0.2}

    available = {k: v for k, v in indicators.items() if k in labels and isinstance(v, (int, float))}
    if not available:
        return ""

    total_weight = sum(weights[k] for k in available)
    composite = sum(available[k] * weights[k] for k in available) / total_weight

    def gauge_color(val):
        if val < 34: return '#3498db'   # 안정
        if val < 67: return '#f1c40f'   # 중립
        return '#e74c3c'                 # 과열/위험

    steps = [
        {'range': [0, 34], 'color': '#eaf4fc'},
        {'range': [34, 67], 'color': '#fdf6e3'},
        {'range': [67, 100], 'color': '#fdecea'},
    ]

    traces = []
    n = len(available)
    for i, (key, val) in enumerate(available.items()):
        traces.append({
            'type': 'indicator',
            'mode': 'gauge+number',
            'value': val,
            'title': {'text': labels[key], 'font': {'size': 14}},
            'number': {'suffix': '°'},
            'gauge': {'axis': {'range': [0, 100]}, 'bar': {'color': gauge_color(val)}, 'steps': steps},
            'domain': {'row': 0, 'column': i},
        })

    traces.append({
        'type': 'indicator',
        'mode': 'gauge+number',
        'value': round(composite, 1),
        'title': {'text': '종합 시장환경 온도계', 'font': {'size': 16}},
        'number': {'suffix': '°', 'font': {'size': 28}},
        'gauge': {'axis': {'range': [0, 100]}, 'bar': {'color': gauge_color(composite)}, 'steps': steps},
        'domain': {'row': 1, 'column': 0, 'x': [0.25, 0.75]},
    })

    layout = {
        'grid': {'rows': 2, 'columns': n, 'pattern': 'independent'},
        'template': 'plotly_white',
        'height': 480,
        'margin': {'t': 40, 'b': 20, 'l': 20, 'r': 20},
    }

    caption = (
        '<p style="font-size:12px;color:#888;margin-top:8px;text-align:center;">'
        '※ 변동성·환율은 최근 실제 데이터 대비 백분위, 인플레이션은 최신 CPI 전년동월대비, '
        '밸류에이션은 참고 밴드 기반 근사치입니다. 종합 온도는 변동성 30%+밸류에이션 30%+환율 20%+인플레이션 20% '
        '가중 평균이며, 자체 산출 방식으로 투자 판단의 근거가 아닌 참고용입니다.'
        '</p>'
    )

    if CHART_MODE == "image":
        img_tag = _plotly_fig_to_img_tag(traces, layout, "시장환경 4대 지표 온도계 및 종합 온도계", width=760, height=480)
        if not img_tag:
            return ""
        return f'<div style="margin:20px auto;max-width:780px;">{img_tag}{caption}</div>'

    chart_id = "macro_thermo_chart"
    plotly_script_id = "macro_thermo_plotly_script"
    chart_js = (
        f'<script>'
        f'(function(){{'
        f'  function initMacroThermo() {{'
        f'    var gd = document.getElementById("{chart_id}");'
        f'    if(!gd) return;'
        f'    var data = {json.dumps(traces, ensure_ascii=False)};'
        f'    var layout = {json.dumps(layout, ensure_ascii=False)};'
        f'    var config = {{responsive: true, displaylogo: false}};'
        f'    Plotly.newPlot(gd, data, layout, config);'
        f'  }}'
        f'  if(window.Plotly) initMacroThermo();'
        f'  else if(!document.getElementById("{plotly_script_id}")) {{'
        f'    var s = document.createElement("script");'
        f'    s.id = "{plotly_script_id}";'
        f'    s.src = "https://cdn.plot.ly/plotly-2.34.0.min.js";'
        f'    s.onload = initMacroThermo;'
        f'    document.head.appendChild(s);'
        f'  }} else {{'
        f'    document.getElementById("{plotly_script_id}").addEventListener("load", initMacroThermo);'
        f'  }}'
        f'}})();'
        f'</script>'
    )

    return (
        f'<div style="margin:20px auto;max-width:780px;">'
        f'<div id="{chart_id}" style="width:100%;"></div>'
        f'{chart_js}'
        f'{caption}'
        f'</div>'
    )

__all__ = [k for k in dir() if not k.startswith('__')]
