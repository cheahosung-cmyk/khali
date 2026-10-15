import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd
from stock_analyst.quality import apply_gates, apply_decisions, last_completed_session
from stock_analyst.tracking import evaluate, build_evaluation, save_snapshot, mark_published, load_history
from stock_analyst.report import build_report
from stock_analyst.verify import _set_news, _flag_news
from datetime import datetime, timezone

AT = '2026-10-15T22:10:00+00:00'
PUB = '2026-10-02T22:10:00+00:00'
ASOF = '2026-10-15T22:10:00+00:00'


def candidate(ticker='TEST', sector='Energy'):
    return dict(ticker=ticker, name=ticker, price=100, price_date='2026-10-15', per=10,
                pbr=1, roe_pct=10, div_pct=0, news_status='ok', warning_flags=[],
                sector=sector, fundamental_asof='2026-06-30', composite_score=75, market_cap_usd_bn=10,
                week52_position=.8, return_60d_pct=10, value_score=70, momentum_score=80)


def markets(candidates=None):
    return ({'date':'-', 'candidates':[], 'scanned':0, 'note':'이번 실행에서 제외'},
            {'date':'2026-10-15', 'candidates':candidates or [candidate()], 'scanned':500,
             'quality':{'price_coverage':1.0, 'fundamental_coverage':1.0}})


def prices():
    idx = pd.to_datetime(['2026-10-05','2026-10-06','2026-10-07','2026-10-08','2026-10-09','2026-10-12'])
    return {'TEST':pd.Series([100,101,102,103,104,110], index=idx),
            '^GSPC':pd.Series([100,100,100,100,100,105], index=idx)}


class QualityTests(unittest.TestCase):
    def test_holidays_and_unfinished_bar(self):
        self.assertEqual(last_completed_session('US','2026-07-03T22:00:00Z'), '2026-07-02')
        self.assertEqual(last_completed_session('KR','2026-10-09T08:00:00Z'), '2026-10-08')
        self.assertEqual(last_completed_session('US','2026-10-15T15:00:00Z'), '2026-10-14')

    def test_missing_news_cannot_be_overridden(self):
        kr, us = markets()
        us['candidates'][0]['news_status']='failed'
        apply_gates(kr,us,AT)
        apply_decisions(kr,us,[dict(market='US',ticker='TEST',decision='pass',confidence='상')])
        self.assertEqual(us['candidates'][0]['decision'],'observe')
        self.assertEqual(us['candidates'][0]['allocation_pct'],0)

    def test_stale_candidate_even_when_market_fresh(self):
        kr, us = markets()
        us['candidates'][0]['price_date']='2026-10-14'
        apply_gates(kr,us,AT)
        self.assertEqual(us['candidates'][0]['gate_status'],'observe')

    def test_coverage_threshold(self):
        kr,us=markets()
        us['quality']['price_coverage']=.89
        apply_gates(kr,us,AT)
        self.assertTrue(us['recommendations_blocked'])
        self.assertEqual(us['status'],'partial')

    def test_nan_price_and_missing_dividend(self):
        for key,value in [('price',float('nan')),('div_pct',None)]:
            kr,us=markets()
            us['candidates'][0][key]=value
            apply_gates(kr,us,AT)
            self.assertEqual(us['candidates'][0]['gate_status'],'observe')

    def test_caps_and_atomic_invalid_response(self):
        kr,us=markets([candidate(str(i)) for i in range(6)])
        apply_gates(kr,us,AT)
        decisions=[dict(market='US',ticker=str(i),decision='pass',confidence='상') for i in range(6)]
        with self.assertRaises(ValueError):
            apply_decisions(kr,us,decisions+[dict(market='US',ticker='UNKNOWN',decision='pass',confidence='中')])
        self.assertTrue(all(c['decision']=='observe' for c in us['candidates']))
        apply_decisions(kr,us,decisions)
        self.assertEqual(sum(c['allocation_pct'] for c in us['candidates']),25)
        self.assertLessEqual(max(c['allocation_pct'] for c in us['candidates']),10)
        self.assertTrue(all(c['confidence']!='상' for c in us['candidates']))

    def test_undated_old_future_and_failed_news(self):
        c={}
        now=datetime(2026,10,15,tzinfo=timezone.utc)
        _set_news(c,[{'title':'no date'},{'title':'old','pubDate':'2026-09-01T00:00:00Z'},
                     {'title':'future','pubDate':'2026-10-16T00:00:00Z'}],now)
        self.assertEqual(c['news_status'],'empty_or_undated')
        _set_news(c,[{'title':'Company faces lawsuit','pubDate':'2026-10-14T00:00:00Z'}],now)
        self.assertEqual(c['news_status'],'ok')
        self.assertTrue(c['warning_flags'])


class TrackingTests(unittest.TestCase):
    def test_fixed_horizon_exact_dates_and_costs(self):
        c={'market':'US','ticker':'TEST'}
        r=evaluate(c,PUB,ASOF,prices(),5,20)
        self.assertEqual(r['entry_date'],'2026-10-05')
        self.assertEqual(r['exit_date'],'2026-10-12')
        self.assertAlmostEqual(r['return'],.10)
        self.assertAlmostEqual(r['excess'],.05)
        self.assertLess(r['net_return'],r['return'])

    def test_no_future_leakage(self):
        r=evaluate({'market':'US','ticker':'TEST'},PUB,'2026-10-09T22:00:00Z',prices(),5)
        self.assertEqual(r['status'],'pending')
        self.assertIsNone(r['return'])

    def test_no_substitution_for_missing_entry_or_exit(self):
        for date in ('2026-10-05','2026-10-12'):
            p=prices()
            p['TEST']=p['TEST'].drop(pd.Timestamp(date))
            self.assertEqual(evaluate({'market':'US','ticker':'TEST'},PUB,ASOF,p,5)['status'],'missing_price')

    def test_missing_benchmark_separate_denominator(self):
        p=prices();p.pop('^GSPC')
        result=build_evaluation([{'date':'2026-10-02','available_at':PUB,'candidates':[{'market':'US','ticker':'TEST'}]}],p,ASOF)
        g=result['groups']['quant:US:5']
        self.assertEqual((g['evaluated'],g['excess_n']),(1,0))

    def test_rejected_not_final_legacy_not_fabricated(self):
        e=[{'schema_version':2,'date':'2026-10-02','available_at':PUB,'candidates':[
            {'market':'US','ticker':'TEST','decision':'reject'},
            {'market':'US','ticker':'TEST','decision':'pass'}]},
           {'date':'2026-10-01','candidates':[{'market':'US','ticker':'TEST'}]}]
        r=build_evaluation(e,prices(),ASOF)
        self.assertEqual(r['groups']['quant:US:5']['evaluated'],2)
        self.assertEqual(r['groups']['final:US:5']['evaluated'],1)
        self.assertEqual(r['groups']['quant:US:5']['status_counts']['unknown_publication_time'],1)

    def test_duplicates_and_invalid_prices_fail_closed(self):
        for s in [pd.Series([100,110],index=pd.to_datetime(['2026-10-05']*2)),
                  pd.Series([0,110],index=pd.to_datetime(['2026-10-05','2026-10-12']))]:
            p=prices();p['TEST']=s
            self.assertNotEqual(evaluate({'market':'US','ticker':'TEST'},PUB,ASOF,p,5)['status'],'ok')

    def test_snapshot_reruns_preserve_original_and_publication(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'2026-10-15.json';p.write_text('{"date":"2026-10-15","candidates":[]}')
            old=p.read_bytes()
            a=save_snapshot(td,'2026-10-15',{}, {})
            b=save_snapshot(td,'2026-10-15',{}, {})
            self.assertNotEqual(a,b)
            self.assertEqual(p.read_bytes(),old)
            mark_published(a,'2027-01-01T00:00:00Z','https://example.test')
            with self.assertRaises(ValueError):
                mark_published(a,'2027-01-02T00:00:00Z','https://example.test')

    def test_publication_second_precision_is_conservative(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'run.json'
            p.write_text(json.dumps({'generated_at':'2026-10-15T22:10:00.800000Z','available_at':None}))
            mark_published(p,'2026-10-15T22:10:00Z','https://example.test/1')
            d=json.loads(p.read_text())
            self.assertEqual(d['available_at'],'2026-10-15T22:10:01+00:00')
            mark_published(p,'2026-10-15T22:10:00Z','https://example.test/1')

    def test_corrupt_history_reported(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td)/'2026-10-01.json').write_text('broken')
            entries,errors=load_history(td,'2026-10-15')
            self.assertEqual(len(errors),1)


class ReportTests(unittest.TestCase):
    def test_ai_gate_cannot_be_overridden_in_report(self):
        kr,us=markets();us['candidates'][0]['news_status']='failed';apply_gates(kr,us,AT)
        raw=json.dumps({'decisions':[dict(market='US',ticker='TEST',decision='pass',confidence='상',reason='test')]})
        with patch('stock_analyst.report.ai_analysis',return_value=raw):
            text=build_report(kr,us,'2026-10-16',False,tracking_md='CANONICAL_METRICS')
        self.assertIn('관찰·추천 보류',text)
        self.assertEqual(text.count('CANONICAL_METRICS'),1)
        self.assertNotIn('5:0',text)

    def test_invalid_ai_and_no_ai_have_no_final_recommendation(self):
        for raw in ('invalid',json.dumps({'decisions':[]})):
            kr,us=markets();apply_gates(kr,us,AT)
            with patch('stock_analyst.report.ai_analysis',return_value=raw):
                build_report(kr,us,'2026-10-16',False)
            self.assertEqual(us['candidates'][0]['decision'],'observe')


if __name__=='__main__':
    unittest.main()
