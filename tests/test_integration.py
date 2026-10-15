"""네트워크·유료 AI 없이 전체 생성과 신호 백테스트를 실행한다."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd

from stock_analyst.backtest import run
from stock_analyst.main import main
from stock_analyst.quality import apply_gates, apply_decisions
from stock_analyst.tracking import download_prices, build_evaluation, evaluate
from stock_analyst.kr_screener import _fetch_market
from test_validation import markets, prices, AT, ASOF, PUB


class IntegrationTests(unittest.TestCase):
    def test_generate_save_publish_evaluate_contract(self):
        kr,us=markets()
        with tempfile.TemporaryDirectory() as td:
            with patch('sys.argv',['stock_analyst','--dry-run','--out-dir',td]), \
                 patch('stock_analyst.kr_screener.screen',return_value=kr), \
                 patch('stock_analyst.us_screener.screen',return_value=us), \
                 patch('stock_analyst.verify.enrich'), \
                 patch('stock_analyst.main.utc_now',return_value=AT):
                main()
            reports=list((Path(td)/'runs').glob('*.md'))
            snapshots=list((Path(td)/'history'/'runs').glob('*.json'))
            self.assertEqual(len(reports),1)
            self.assertEqual(len(snapshots),1)
            d=json.loads(snapshots[0].read_text())
            self.assertIsNone(d['available_at'])
            self.assertEqual(d['candidates'][0]['decision'],'observe')
            text=reports[0].read_text()
            self.assertIn('고정 거래일 성적표',text)
            self.assertIn('관찰·추천 보류',text)
            self.assertEqual(len(list((Path(td)/'evaluations').glob('*-prices.csv'))),1)

    def test_backtest_fixed_period_costs_and_overlap(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'history').mkdir()
            e={'schema_version':2,'date':'2026-10-02','available_at':PUB,'candidates':[
                {'market':'US','ticker':'TEST','decision':'pass'},
                {'market':'US','ticker':'TEST','decision':'reject'}]}
            (root/'history'/'2026-10-02.json').write_text(json.dumps(e))
            rows=[{'date':str(d.date()),'symbol':s,'close':v} for s,p in prices().items() for d,v in p.items()]
            csv=root/'prices.csv';pd.DataFrame(rows).to_csv(csv,index=False)
            r=run(root/'history',csv,ASOF)
            zero=r['scenarios_round_trip_bps']['0']
            self.assertEqual(zero['all_signals']['quant:US:5']['evaluated'],2)
            self.assertEqual(zero['all_signals']['final:US:5']['evaluated'],1)
            self.assertEqual(zero['no_overlap']['quant:US:5']['evaluated'],1)
            self.assertEqual(zero['no_overlap']['quant:US:5']['status_counts']['overlap_excluded'],1)
            self.assertGreater(zero['all_signals']['quant:US:5']['mean_net_return'],
                               r['scenarios_round_trip_bps']['50']['all_signals']['quant:US:5']['mean_net_return'])

    def test_naver_redesigned_page_is_failure(self):
        session=unittest.mock.Mock()
        session.get.return_value.text='<html><title>Npay 증권</title></html>'
        with self.assertRaisesRegex(ValueError,'테이블 없음'):
            _fetch_market(session,0,'KOSPI')

    def test_download_handles_single_multiindex_and_partial_failure(self):
        p=prices()['TEST']
        frame=pd.DataFrame({('TEST','Close'):p,('MISSING','Close'):float('nan')})
        with patch('yfinance.download',return_value=frame):
            result,errors=download_prices(['TEST','MISSING'],'2026-10-01',ASOF)
        self.assertIn('TEST',result)
        self.assertEqual(len(errors),1)
        with patch('yfinance.download',return_value=frame[['TEST']]):
            result,errors=download_prices(['TEST'],'2026-10-01',ASOF)
        self.assertIn('TEST',result)
        self.assertEqual(errors,[])

    def test_malformed_ai_no_partial_mutation(self):
        for raw in (None,{},['string'],[{'market':'US','ticker':'TEST','decision':'pass','confidence':'중'},{}]):
            kr,us=markets();apply_gates(kr,us,AT)
            with self.assertRaises(ValueError):
                apply_decisions(kr,us,raw)
            self.assertEqual(us['candidates'][0]['decision'],'observe')

    def test_invalid_coverage_is_blocked(self):
        kr,us=markets();us['quality']['price_coverage']=float('nan');apply_gates(kr,us,AT)
        self.assertTrue(us['recommendations_blocked'])

    def test_corrupt_benchmark_preserves_absolute_return(self):
        p=prices();p['^GSPC']=pd.DataFrame({'bad':[1]})
        r=evaluate({'market':'US','ticker':'TEST'},PUB,ASOF,p,5)
        self.assertEqual(r['status'],'ok')
        self.assertIsNone(r['excess'])

    def test_unknown_korean_listing_not_guessed(self):
        r=evaluate({'market':'KR','ticker':'005930'},PUB,ASOF,{},5)
        self.assertEqual(r['status'],'unknown_listing_market')
