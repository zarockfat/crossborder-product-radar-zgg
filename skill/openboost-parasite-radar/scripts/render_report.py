#!/usr/bin/env python3
"""Validate evidence references and render a standalone offline report."""
import argparse
import html
import json
import math
from pathlib import Path
import re
from urllib.parse import quote, urlparse


def esc(value):
    return html.escape(str(value), quote=True)


def pointer(document, path):
    if path == '':
        return document
    if not path.startswith('/'):
        raise ValueError('JSON Pointer must start with /')
    for part in path[1:].split('/'):
        key = part.replace('~1', '/').replace('~0', '~')
        document = document[int(key)] if isinstance(document, list) else document[key]
    return document


def validate(report, base):
    for key in ['title', 'market', 'updated_at', 'scope', 'verdict', 'hosts', 'opportunities', 'evidence']:
        if key not in report:
            raise ValueError('Missing report field: ' + key)
    ids = set()
    for item in report['evidence'] + report['hosts'] + report['opportunities']:
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', item['id']) or item['id'] in ids:
            raise ValueError('Invalid or duplicate ID: ' + item['id'])
        ids.add(item['id'])
    evidence = {e['id'] for e in report['evidence']}
    hosts = {h['id'] for h in report['hosts']}
    for e in report['evidence']:
        for key in ['tool', 'source_id', 'retrieved_at', 'summary', 'excerpt', 'raw_file', 'pointer']:
            if key not in e:
                raise ValueError('Missing evidence field: ' + key)
        raw = (base / e['raw_file']).resolve()
        if not raw.is_relative_to(base.resolve()) or raw.suffix != '.json':
            raise ValueError('Evidence file must be a JSON inside report directory.')
        if e['tool'] == 'account_info':
            raise ValueError('Account data must not enter reports.')
        record = json.loads(raw.read_text())
        if record.get('tool') != e['tool'] or record.get('retrieved_at') != e['retrieved_at']:
            raise ValueError('Evidence metadata differs from raw record: ' + e['id'])
        pointer(record, e['pointer'])
    for h in report['hosts']:
        if not set(h['evidence']) <= evidence:
            raise ValueError('Unknown host evidence')
    for o in report['opportunities']:
        if o['host_id'] not in hosts or o['status'] not in ['可进入低成本验证', '待验证', '淘汰']:
            raise ValueError('Invalid host or status')
        for field in ['support', 'against']:
            for claim in o[field]:
                if not set(claim['evidence']) <= evidence:
                    raise ValueError('Unknown claim evidence')
        econ = o.get('economics')
        if econ:
            for key in ['sale_price', 'fee_pct', 'fulfillment', 'ad_cost', 'return_reserve', 'target_margin_pct']:
                value = econ[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    raise ValueError('Invalid cost assumption: ' + key)
                if key.endswith('_pct') and value > 100:
                    raise ValueError('Percentage must be <=100')
            if econ['sale_price'] <= 0 or not econ.get('assumptions'):
                raise ValueError('Positive price and explicit assumptions required')


def refs(ids):
    return ' '.join('<a class="ref" href="#%s">%s ↗</a>' % (esc(i), esc(i)) for i in ids)


def claims(items):
    return ''.join('<li>%s <span>%s</span></li>' % (esc(c['text']), refs(c['evidence'])) for c in items) or '<li>本轮未取得相应证据。</li>'


def render(report, base):
    validate(report, base)
    hosts = ''.join('<article class="host"><span class="eyebrow">宿主 %s</span><h3>%s</h3><ul>%s</ul>%s</article>' % (esc(h['id']), esc(h['name']), ''.join('<li>'+esc(m)+'</li>' for m in h['metrics']), refs(h['evidence'])) for h in report['hosts'])
    cards = []
    for o in report['opportunities']:
        econ = o.get('economics')
        calculator = ''
        if econ:
            fields = [('sale_price','售价'),('fee_pct','平台费率 %'),('fulfillment','单件履约'),('ad_cost','单件广告'),('return_reserve','售后预留'),('target_margin_pct','目标贡献利润率 %')]
            inputs = ''.join('<label>%s<input data-key="%s" type="number" step="0.01" min="%s" %s value="%s"></label>' % (label, key, '0.01' if key == 'sale_price' else '0', 'max="100"' if key.endswith('_pct') else '', esc(econ[key])) for key,label in fields)
            calculator = '<details><summary>假设测算 · %s</summary><p>%s</p><div class="calc">%s<output aria-live="polite"></output></div></details>' % (esc(econ['currency']),esc(econ['assumptions']),inputs)
        cards.append('''<article class="opportunity" data-status="{status}">
<div class="cardtop"><span class="eyebrow">{id} / {host}</span><span class="badge">{status}</span></div>
<h3>{name}</h3><p class="pain">{pain}</p><p>{hypothesis}</p>
<div class="twocol"><section><h4>支持证据</h4><ul>{support}</ul></section><section><h4>反对证据</h4><ul>{against}</ul></section></div>
<details><summary>展开缺口与专利状态</summary><ul>{unknowns}</ul><p>{patent}</p></details>
<details><summary>最小验证与停止条件</summary><p>{test}</p></details>
{calculator}</article>'''.format(status=esc(o['status']),id=esc(o['id']),host=esc(o['host_id']),name=esc(o['name']),pain=esc(o['pain']),hypothesis=esc(o['hypothesis']),support=claims(o['support']),against=claims(o['against']),unknowns=''.join('<li>'+esc(x)+'</li>' for x in o['unknowns']),patent=esc(o['patent']),test=esc(o['test']),calculator=calculator))
    sources = []
    for e in report['evidence']:
        url = e.get('url', '')
        link = '<a target="_blank" rel="noopener noreferrer" href="%s">来源页面 ↗</a>' % esc(url) if urlparse(url).scheme in ('http','https') else ''
        sources.append('<details class="source" id="%s"><summary>%s · %s</summary><p>%s</p><blockquote>%s</blockquote><p class="meta">%s · %s · %s</p><p class="meta">JSON Pointer: %s</p><a href="%s">原始 JSON ↗</a> %s</details>' % (esc(e['id']),esc(e['id']),esc(e['summary']),esc(e['summary']),esc(e['excerpt']),esc(e['tool']),esc(e['source_id']),esc(e['retrieved_at']),esc(e['pointer']),esc(quote(e['raw_file'],safe='/')),link))
    template = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title>
<style>
:root{color-scheme:dark;--bg:#0c1118;--panel:#151e29;--line:#2b3948;--ink:#edf4f6;--muted:#aab8c4;--mint:#b8f561;--orange:#ffbf79}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.8 system-ui,-apple-system,sans-serif}main{max-width:1120px;margin:auto;padding:56px 28px 80px}a{color:var(--mint);overflow-wrap:anywhere}h1{font-size:clamp(34px,6vw,64px);line-height:1.15;letter-spacing:-2px;margin:20px 0}h2{font-size:26px;margin:42px 0 18px}h3{font-size:23px;line-height:1.5;margin:12px 0}h4{margin:0;color:var(--mint)}p,li{overflow-wrap:anywhere}p{margin:12px 0}.eyebrow{font:12px/1.5 ui-monospace,monospace;letter-spacing:2px;color:var(--mint)}.sub,.meta{color:var(--muted)}.meta{font-size:12px}.verdict{border-left:3px solid var(--mint);padding:16px 24px;background:#17251c;margin:28px 0}.flow{display:flex;flex-wrap:wrap;gap:12px;color:var(--muted);margin:32px 0}.flow span{border:1px solid var(--line);border-radius:30px;padding:7px 16px}.hosts{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}.host,.opportunity{border:1px solid var(--line);border-radius:18px;background:var(--panel);padding:24px}.host h3{font-size:18px}.host ul{padding-left:20px}.opportunity{margin-bottom:24px}.cardtop{display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between}.badge{color:var(--orange);background:#35291d;border-radius:5px;padding:3px 12px;font-size:13px}.pain{font-size:19px;color:#d5e4ed}.twocol{display:grid;grid-template-columns:1fr 1fr;gap:24px;padding:16px 0}.twocol section:nth-child(2) h4{color:var(--orange)}ul{padding-left:22px}.ref{font:12px ui-monospace,monospace;white-space:nowrap;display:inline-block;padding:3px 6px;background:#223421;border-radius:4px;text-decoration:none}details{border-top:1px solid var(--line);padding:14px 0}summary{cursor:pointer;font-weight:600;overflow-wrap:anywhere}summary:hover{color:var(--mint)}.source{scroll-margin-top:20px}.source:target{outline:1px solid var(--mint);padding:18px;border-radius:12px}blockquote{border-left:2px solid var(--orange);padding:8px 16px;margin:16px 0;color:#e4c6a4;white-space:pre-wrap}.filters{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}button{font:inherit;font-size:14px;cursor:pointer;background:transparent;color:var(--muted);padding:8px 16px;border:1px solid var(--line);border-radius:8px}button.active{color:#0c1118;background:var(--mint);border-color:var(--mint)}button:focus-visible,summary:focus-visible,a:focus-visible{outline:2px solid var(--mint);outline-offset:4px}.calc{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.calc label{font-size:13px;color:var(--muted)}input{display:block;width:100%;padding:10px;border-radius:6px;border:1px solid var(--line);background:var(--bg);color:var(--ink);font-size:16px}output{grid-column:1/-1;color:var(--mint);padding:12px;background:#17251c}.empty{color:var(--muted)}footer{margin-top:44px;border-top:1px solid var(--line);padding-top:18px;color:var(--muted);font-size:13px}[hidden]{display:none!important}@media(max-width:640px){main{padding:28px 16px}.twocol{grid-template-columns:1fr}.opportunity,.host{padding:18px}.calc{grid-template-columns:1fr 1fr}}@media print{body{background:white;color:black}.host,.opportunity{break-inside:avoid}.filters{display:none}}
</style><main><div class="eyebrow">OPENBOOST / PRODUCT RADAR</div><h1>爆款没解决的，<br>就是下一道问题。</h1><p class="sub">__TITLE__ · __MARKET__</p><p class="meta">__UPDATED__ · __SCOPE__</p><div class="verdict">__VERDICT__</div><nav class="flow" aria-label="调查路径"><span>01 宿主</span><span>02 真实痛点</span><span>03 补位方案</span><span>04 支持 / 反证</span><span>05 最小验证</span></nav>
<h2>先确认，借谁的需求</h2><div class="hosts">__HOSTS__</div><h2>机会候选 · 允许全部不通过</h2><div class="filters" role="group" aria-label="按结论筛选"><button class="active" data-filter="全部" aria-pressed="true">全部</button><button data-filter="可进入低成本验证" aria-pressed="false">可进入低成本验证</button><button data-filter="待验证" aria-pressed="false">待验证</button><button data-filter="淘汰" aria-pressed="false">淘汰</button></div><div id="cards">__CARDS__</div><p class="empty" id="empty" hidden>这个筛选下暂无候选。没有结果，也是一种结果。</p><h2>每个判断，都能回到证据</h2>__SOURCES__<footer>基于 OpenBoost 接口的数据调查 · 事实、推断与假设分开记录。数据覆盖与时效以各证据为准；候选不等于备货建议。</footer></main>
<script>
document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('[data-filter]').forEach(x=>{x.classList.toggle('active',x===b);x.setAttribute('aria-pressed',String(x===b))});let count=0;document.querySelectorAll('.opportunity').forEach(c=>{c.hidden=b.dataset.filter!=='全部'&&c.dataset.status!==b.dataset.filter;if(!c.hidden)count++});document.getElementById('empty').hidden=count>0}));
function reveal(){const el=document.getElementById(location.hash.slice(1));if(el&&el.tagName==='DETAILS')el.open=true}window.addEventListener('hashchange',reveal);reveal();document.querySelectorAll('.ref').forEach(a=>a.addEventListener('click',()=>{const el=document.getElementById(a.hash.slice(1));if(el)el.open=true}));
document.querySelectorAll('.calc').forEach(calc=>{function update(){let v={};let valid=true;calc.querySelectorAll('input').forEach(i=>{v[i.dataset.key]=Number(i.value);if(i.value===''||!i.checkValidity()||!Number.isFinite(Number(i.value)))valid=false});let out=calc.querySelector('output');if(!valid){out.textContent='请填写有效且非负的数值；售价需大于0，比例不超过100%。';return}const max=v.sale_price*(1-v.fee_pct/100-v.target_margin_pct/100)-v.fulfillment-v.ad_cost-v.return_reserve;out.textContent=max<0?'这组假设下不可行：采购及头程上限为 '+max.toFixed(2):'假设下，单件采购 + 头程上限：'+max.toFixed(2)+'（同上方币种；不是实际利润）'}calc.addEventListener('input',update);update()});
document.getElementById('empty').hidden=document.querySelectorAll('.opportunity').length>0;
</script></html>'''
    values = {'TITLE':esc(report['title']),'MARKET':esc(report['market']),'UPDATED':esc(report['updated_at']),'SCOPE':esc(report['scope']),'VERDICT':esc(report['verdict']),'HOSTS':hosts,'CARDS':''.join(cards),'SOURCES':''.join(sources)}
    return re.sub(r'__(TITLE|MARKET|UPDATED|SCOPE|VERDICT|HOSTS|CARDS|SOURCES)__',lambda m:values[m.group(1)],template)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report');p.add_argument('--out',required=True);args=p.parse_args()
    source=Path(args.report).resolve();out=Path(args.out).resolve()
    if out.parent != source.parent:
        raise ValueError('HTML and report.json must share a directory for relative evidence links.')
    document=render(json.loads(source.read_text()),source.parent)
    with out.open('x') as f:f.write(document)
    print(str(out))


if __name__=='__main__':
    main()
