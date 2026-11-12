/* HackerRig — 纯前端查询逻辑。离线、无外部依赖。
   数据来自同目录 data.js（window.HACKERRIG_DATA）。
   网址同步用 hash（file:// 双击打开也能还原）；中位数按「每人每机器每模型一票」，样本<5 不给。
   第六步：搜索去抖+局部刷新（保焦点）；第三问计数用总数、多卡单列；口径锚点不重置视图；
           卡片新增 扩散/跑不动/投机解码/多卡/补自上文 徽章；去掉内部 tier 标签。 */
(function () {
  'use strict';
  var DATA = window.HACKERRIG_DATA;
  if (!DATA) { document.body.insertAdjacentHTML('afterbegin', '<p class="empty">数据未加载：缺少 data.js</p>'); return; }
  var META = DATA.meta, RECS = DATA.records, CATS = META.category_order;

  // 计数口径：亲测 + 去重 keep。重复报告单列、标注，不计数。
  var STAT = RECS.filter(function (r) { return r.first_person === true && r.dedup_status === 'keep'; });
  var DUPS = RECS.filter(function (r) { return r.first_person === true && r.dedup_status === 'duplicate'; });
  var REGRET = RECS.filter(function (r) { return r.first_person === true && r.sentiment === 'regret'; });

  /* ---------- 工具 ---------- */
  function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function round2(v) { return Math.round(v * 100) / 100; }
  function median(a) {
    if (!a.length) return null;
    var s = a.slice().sort(function (x, y) { return x - y; });
    var m = Math.floor(s.length / 2);
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  }
  function fmtNum(v) {
    if (v === null || v === undefined) return '—';
    return (Math.round(v) === v) ? String(v) : String(round2(v));
  }
  function debounce(fn, ms) {
    var t; return function () { var a = arguments, c = this; clearTimeout(t); t = setTimeout(function () { fn.apply(c, a); }, ms); };
  }
  function speedEligible(r) {
    return r.first_person === true && r.dedup_status === 'keep' && r.speed_stat === 'include'
      && r.speed_value !== null && r.speed_value !== undefined && r.speed_unit === 'tok/s'
      && (r.speed_kind === 'generation' || r.speed_kind === 'unspecified')
      && !r.speculative && !r.diffusion && !r.stalled;
  }
  // 每人每机器每模型一票（本人中位数），再取票的中位数；样本<5 不给中位数。
  function personStats(recs) {
    var el = recs.filter(speedEligible), n = el.length, g = {};
    el.forEach(function (r) {
      var k = r.by + '||' + (r.machine_canon || '') + '||' + (r.model_canon || '');
      (g[k] = g[k] || []).push(r.speed_value);
    });
    var votes = Object.keys(g).map(function (k) { return median(g[k]); });
    var vals = el.map(function (r) { return r.speed_value; });
    return {
      n: n, votes: votes.length,
      median: n >= 5 ? round2(median(votes)) : null,
      min: vals.length ? Math.min.apply(null, vals) : null,
      max: vals.length ? Math.max.apply(null, vals) : null
    };
  }
  function sentimentCounts(recs) {
    var c = { satisfied: 0, mixed: 0, regret: 0, neutral: 0, none: 0 };
    recs.forEach(function (r) { c[r.sentiment || 'none'] = (c[r.sentiment || 'none'] || 0) + 1; });
    return c;
  }
  // 后悔按人小结：每类机器多少人报过亲测(STAT=fp+keep)、其中多少人后悔、比例；合计按人去重。
  // 一人多条只算一人，避免一个人反复抱怨把一类机器顶上去；卡片仍全列。
  function regretPersonSummary() {
    function ppl(recs, cat) {
      var s = {};
      recs.forEach(function (r) { if ((r.machine_category || null) === cat) s[r.by] = 1; });
      return Object.keys(s).length;
    }
    function distinct(recs) { var s = {}; recs.forEach(function (r) { s[r.by] = 1; }); return Object.keys(s).length; }
    function pct(r, m) { return m ? (Math.round(r / m * 1000) / 10) : 0; }
    var regStat = STAT.filter(function (r) { return r.sentiment === 'regret'; });
    var rows = CATS.map(function (c) { return { cat: c, m: ppl(STAT, c), r: ppl(regStat, c) }; })
      .filter(function (x) { return x.m > 0; });
    var mu = ppl(STAT, null), ru = ppl(regStat, null);
    var tm = distinct(STAT), tr = distinct(regStat);
    function row(label, m, r, total) {
      return '<tr' + (total ? ' class="sum-row"' : '') + '><td data-label="类别">' + label + '</td>'
        + '<td class="num" data-label="报过亲测">' + m + ' 人</td>'
        + '<td class="num" data-label="其中后悔">' + r + ' 人</td>'
        + '<td class="num" data-label="后悔比例">' + pct(r, m) + '%</td></tr>';
    }
    var body = rows.map(function (x) { return row(catBadge(x.cat), x.m, x.r); }).join('');
    if (mu) body += row('<span class="cat">机器未指明</span>', mu, ru);
    body += row('合计（按人去重）', tm, tr, true);
    return '<p class="small" style="margin:0 0 .5rem"><strong>后悔按人算</strong>（一人多条只算一人）：每类机器多少人报过亲测、其中多少人后悔。</p>'
      + '<div class="tbl-scroll"><table class="tbl regret-person-tbl"><thead><tr><th>机器类别</th><th class="num">报过亲测</th><th class="num">其中后悔</th><th class="num">后悔比例</th></tr></thead><tbody>'
      + body + '</tbody></table></div>'
      + '<p class="small muted" style="margin:.5rem 0 0">同一人可在多类机器下各计一次，故各类人数相加多于合计；合计按人去重。后悔卡片仍全列 ' + REGRET.length + ' 条（一人多条都列）。</p>';
  }
  var SENT_LABEL = { satisfied: '满意', mixed: '褒贬不一', regret: '后悔', neutral: '中性', none: '未表态' };
  var KIND_LABEL = { generation: '生成', prompt: '提示处理', total: '总吞吐', unspecified: '未注明' };
  var FLAG_LABEL = {
    'E_极低': '极低速度', 'D_高速待核': '高速待核', 'B_增量相对': '增量/相对值',
    'A_存疑保留': '存疑保留', 'C_单位异常': '单位异常', 'F_字符级非典型': '字符级非典型'
  };
  function catBadge(cat) {
    if (!cat) return '<span class="cat">未分类</span>';
    return '<span class="cat" data-c="' + esc(cat) + '">' + esc(cat) + '</span>';
  }
  function sentBadge(s) {
    var key = s || 'none';
    return '<span class="badge sent-' + esc(key) + '">' + esc(SENT_LABEL[key] || key) + '</span>';
  }
  function countBy(recs, field) {
    var c = {};
    recs.forEach(function (r) { var v = r[field]; if (v !== null && v !== undefined && v !== '') c[v] = (c[v] || 0) + 1; });
    return c;
  }
  function sortedEntries(counts) {
    return Object.keys(counts).map(function (k) { return [k, counts[k]]; })
      .sort(function (a, b) { return b[1] - a[1] || a[0].localeCompare(b[0], 'zh'); });
  }
  function machineCat(name) {
    var r = STAT.find(function (x) { return x.machine_canon === name; });
    return r ? r.machine_category : null;
  }

  /* ---------- 网址同步（hash，file:// 安全） ---------- */
  var applyingHash = false;
  function readState(defaults) {
    var qs = location.hash.replace(/^#/, '');
    if (!qs && location.search) qs = location.search.replace(/^\?/, '');
    var p = new URLSearchParams(qs), s = {};
    Object.keys(defaults).forEach(function (k) {
      var d = defaults[k];
      if (p.has(k)) {
        var v = p.get(k);
        s[k] = (typeof d === 'boolean') ? (v === '1' || v === 'true') : v;
      } else { s[k] = d; }
    });
    return s;
  }
  function writeState(s, defaults) {
    var p = new URLSearchParams();
    Object.keys(defaults).forEach(function (k) {
      var v = s[k], d = defaults[k];
      if (typeof d === 'boolean') { if (v) p.set(k, '1'); }
      else if (v !== null && v !== undefined && v !== '' && v !== d) p.set(k, v);
    });
    var qs = p.toString();
    var target = location.pathname + (qs ? '#' + qs : '');
    try { history.replaceState(null, '', target); }
    catch (e) { applyingHash = true; location.hash = qs; }
  }
  function syncControls(root, s) {
    root.querySelectorAll('[data-k]').forEach(function (el) {
      var k = el.getAttribute('data-k');
      if (!(k in s)) return;
      if (el.type === 'checkbox') el.checked = !!s[k];
      else el.value = s[k];
    });
  }

  /* ---------- 卡片 ---------- */
  function speedBlock(r) {
    // 区间速度：卡片显示原文，注明取中点进统计
    if (r.range_converted && r.speed_raw) {
      var tag = ' 中点 ' + esc(fmtNum(r.speed_value)) + (r.speed_stat === 'include' ? ' 进统计' : '');
      return '<span class="card-speed mono">' + esc(r.speed_raw) + '<span class="u">' + tag + '</span></span>';
    }
    if (r.speed_value !== null && r.speed_value !== undefined) {
      var note = '';
      if (r.speed_converted && !r.range_converted) note = '<span class="u"> 原文 ' + esc(fmtNum(r.speed_value_original)) + ' ' + esc(r.speed_unit_original) + '</span>';
      else if (r.speed_kind && r.speed_kind !== 'generation' && r.speed_kind !== 'unspecified') note = '<span class="u"> ' + esc(KIND_LABEL[r.speed_kind] || r.speed_kind) + '</span>';
      return '<span class="card-speed mono">' + esc(fmtNum(r.speed_value)) + '<span class="u"> tok/s</span>' + note + '</span>';
    }
    if (r.speed_raw) return '<span class="card-speed mono na">' + esc(r.speed_raw) + '</span>';
    return '<span class="card-speed na">速度未注明</span>';
  }
  function specLine(r) {
    var items = [['内存', r.memory], ['参数', r.params_canon], ['量化', r.quant_canon],
      ['引擎', r.engine_canon], ['上下文', r.context_length], ['并发', r.concurrency], ['价格', r.price]];
    var html = items.filter(function (it) { return it[1] !== null && it[1] !== undefined && it[1] !== ''; })
      .map(function (it) { return '<span><span class="k">' + esc(it[0]) + '</span> ' + esc(it[1]) + '</span>'; }).join('');
    return html ? '<div class="specs">' + html + '</div>' : '';
  }
  function badges(r) {
    var b = [sentBadge(r.sentiment)];
    if (r.diffusion) b.push('<span class="badge diffusion" title="扩散文本模型，tok/s 与自回归不可比">扩散模型</span>');
    if (r.stalled) b.push('<span class="badge stalled" title="0.0 tok/s，视为跑不动">跑不动</span>');
    if (r.speculative) b.push('<span class="badge spec" title="' + esc(r.spec_method || '投机解码开启') + '">投机解码' + (r.spec_method ? '·' + esc(r.spec_method) : '') + '</span>');
    if (r.multi_card) b.push('<span class="badge multi" title="' + (r.gpu_count ? esc(r.gpu_count) + ' 卡/机' : '多卡或多机') + '">多卡/多机</span>');
    if (r.speed_stat === 'exclude') b.push('<span class="badge exclude" title="' + esc(r.speed_stat_reason || '') + '">不计入速度统计</span>');
    if (r.dedup_status === 'duplicate') b.push('<span class="badge dup">重复报告（不计数）</span>');
    (r.anomaly_flags || []).forEach(function (f) { b.push('<span class="badge">' + esc(FLAG_LABEL[f] || f) + '</span>'); });
    if (r.context_supplemented) {
      var href = r.context_ancestor_id ? 'https://news.ycombinator.com/item?id=' + esc(r.context_ancestor_id) : (r.hn_url || '#');
      b.push('<a class="badge supplement" href="' + href + '" target="_blank" rel="noopener noreferrer" title="机器/模型等信息补自父评论或故事标题，点击看那条评论">补自上文</a>');
    }
    return '<div class="badges">' + b.join('') + '</div>';
  }
  function evidenceBlock(r) {
    var ev = r.evidence_en || [];
    var html = '';
    if (ev.length) {
      html += '<div class="evidence">' + ev.map(function (q) { return '<p>“' + esc(q) + '”</p>'; }).join('') + '</div>';
    }
    var ctx = r.context_evidence_en || [];
    if (ctx.length) {
      html += '<details class="ev-toggle"><summary>上下文证据（父评论）</summary><div class="evidence">'
        + '<span class="ctx-label">CONTEXT</span>'
        + ctx.map(function (q) { return '<p>“' + esc(q) + '”</p>'; }).join('') + '</div></details>';
    }
    return html;
  }
  function cardHTML(r) {
    var machine = r.machine_canon || r.machine || '机器未指明';
    var model = r.model_canon || r.model || '模型未指明';
    var date = (r.time || '').slice(0, 10);
    return '<article class="card' + (r.dedup_status === 'duplicate' ? ' dup' : '') + '" id="r-' + esc(r.record_id) + '">'
      + '<div class="card-top">'
      + '<span class="card-machine">' + esc(machine) + '</span>' + catBadge(r.machine_category)
      + '<span class="card-model">' + esc(model) + '</span>'
      + speedBlock(r)
      + '</div>'
      + specLine(r)
      + badges(r)
      + (r.summary_zh ? '<p class="card-summary">' + esc(r.summary_zh) + '</p>' : '')
      + evidenceBlock(r)
      + '<div class="card-foot">'
      + '<span>' + esc(r.by || '匿名') + '</span><span>' + esc(date) + '</span>'
      + '<a href="' + esc(r.hn_url) + '" target="_blank" rel="noopener noreferrer">HN 原帖 →</a>'
      + '</div></article>';
  }

  /* ---------- 卡片列表 + 筛选条（筛选条 DOM 稳定，搜索去抖局部刷新，保焦点） ---------- */
  function filterCards(recs, s) {
    var out = recs.slice();
    if (s.cat) out = out.filter(function (r) { return r.machine_category === s.cat; });
    if (s.sent) out = out.filter(function (r) { return (r.sentiment || 'none') === s.sent; });
    if (s.q) {
      var q = s.q.toLowerCase();
      out = out.filter(function (r) {
        return [r.summary_zh, r.machine_canon, r.machine, r.model_canon, r.model, r.by, (r.evidence_en || []).join(' ')]
          .join(' ').toLowerCase().indexOf(q) >= 0;
      });
    }
    var sort = s.sort || 'speed_desc';
    out.sort(function (a, b) {
      if (sort === 'time_desc') return (b.time || '').localeCompare(a.time || '');
      if (sort === 'machine') return (a.machine_canon || '').localeCompare(b.machine_canon || '', 'zh');
      var av = a.speed_value, bv = b.speed_value;
      if (av === null || av === undefined) av = -Infinity;
      if (bv === null || bv === undefined) bv = -Infinity;
      return sort === 'speed_asc' ? av - bv : bv - av;
    });
    return out;
  }
  function cardFilterBar(s, opts) {
    var catOpts = '<option value="">全部类别</option>' + CATS.map(function (c) {
      return '<option value="' + esc(c) + '"' + (s.cat === c ? ' selected' : '') + '>' + esc(c) + '</option>';
    }).join('');
    var sentOpts = [['', '全部态度'], ['satisfied', '满意'], ['mixed', '褒贬不一'], ['regret', '后悔'], ['neutral', '中性'], ['none', '未表态']]
      .map(function (o) { return '<option value="' + o[0] + '"' + (s.sent === o[0] ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('');
    var sortOpts = [['speed_desc', '速度从高到低'], ['speed_asc', '速度从低到高'], ['time_desc', '时间从新到旧'], ['machine', '按机器名']]
      .map(function (o) { return '<option value="' + o[0] + '"' + (s.sort === o[0] ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('');
    return '<div class="controls">'
      + (opts.showCat ? '<div class="field"><label>机器类别</label><select data-k="cat">' + catOpts + '</select></div>' : '')
      + '<div class="field"><label>态度</label><select data-k="sent">' + sentOpts + '</select></div>'
      + '<div class="field"><label>排序</label><select data-k="sort">' + sortOpts + '</select></div>'
      + '<div class="field field-search"><label>搜索（机器/模型/摘要/原文/作者）</label><input type="search" data-k="q" value="' + esc(s.q) + '" placeholder="输入关键词"></div>'
      + '<label class="dup-toggle"><input type="checkbox" data-k="dups"' + (s.dups ? ' checked' : '') + '> 显示重复报告</label>'
      + '</div>';
  }
  // opts: {showCat, sync(s)}。sync 只写网址不重渲染整视图；refresh 只换卡片列表。
  function renderCards(container, recs, s, opts) {
    container.innerHTML = '<div class="card-controls">' + cardFilterBar(s, opts) + '</div><div class="card-list"></div>';
    var listEl = container.querySelector('.card-list');
    function refresh() {
      var base = recs.slice();
      if (s.dups) {
        var ids = {}; base.forEach(function (r) { ids[r.record_id] = 1; });
        DUPS.forEach(function (d) {
          var match = recs.some(function (r) { return r.machine_canon === d.machine_canon && r.model_canon === d.model_canon; });
          if (match && !ids[d.record_id]) base.push(d);
        });
      }
      var filtered = filterCards(base, s);
      listEl.innerHTML = '<p class="result-count">显示 ' + filtered.length + ' 条' + (s.dups ? '（含重复报告）' : '（亲测·去重）') + '</p>'
        + (filtered.length ? '<div class="cards">' + filtered.map(cardHTML).join('') + '</div>'
          : '<div class="empty">没有符合条件的实测。试试放宽筛选。</div>');
    }
    var sync = opts.sync || function () {};
    container.querySelectorAll('.card-controls [data-k]').forEach(function (el) {
      var k = el.getAttribute('data-k');
      if (el.type === 'search') {
        var dr = debounce(function () { sync(s); refresh(); }, 120);
        el.addEventListener('input', function () { s.q = el.value; dr(); });
      } else {
        el.addEventListener('change', function () { s[k] = (el.type === 'checkbox') ? el.checked : el.value; sync(s); refresh(); });
      }
    });
    refresh();
  }

  /* ---------- 视图级控件绑定（选择器/按钮 → 整视图重渲染） ---------- */
  function bindControls(root, s, commitFn) {
    root.querySelectorAll('.controls [data-k]').forEach(function (el) {
      var k = el.getAttribute('data-k');
      el.addEventListener('change', function () {
        s[k] = (el.type === 'checkbox') ? el.checked : el.value;
        commitFn(s);
      });
    });
  }

  /* ---------- 视图：第三问 对比（同模型跨类别，多卡单列） ---------- */
  function modelOptions(selected) {
    var counts = sortedEntries(countBy(STAT, 'model_canon'));
    return counts.map(function (e) {
      return '<option value="' + esc(e[0]) + '"' + (selected === e[0] ? ' selected' : '') + '>' + esc(e[0]) + '（' + e[1] + '）</option>';
    }).join('');
  }
  function renderCompare(root, s) {
    var model = s.model || META.default_compare_model;
    var subset = STAT.filter(function (r) { return r.model_canon === model; });
    var single = subset.filter(function (r) { return !r.multi_card; });
    var multi = subset.filter(function (r) { return r.multi_card; });
    var overall = personStats(single);
    function mkRow(cat, rs) {
      var mc = sortedEntries(countBy(rs, 'machine_canon')).slice(0, 3).map(function (e) { return e[0] + '×' + e[1]; });
      return { cat: cat, n: rs.length, ps: personStats(rs), sent: sentimentCounts(rs), machines: mc };
    }
    var rows = CATS.map(function (cat) {
      var rs = single.filter(function (r) { return r.machine_category === cat; });
      return rs.length ? mkRow(cat, rs) : null;
    }).filter(Boolean);
    var multiRow = multi.length ? mkRow('多卡/多机', multi) : null;
    var allRows = multiRow ? rows.concat([multiRow]) : rows;
    var uncat = single.filter(function (r) { return !r.machine_category; }).length;
    var maxMed = Math.max.apply(null, allRows.map(function (r) { return r.ps.median || 0; }).concat([1]));

    function statBlock(r) {
      var hasMed = r.ps.median !== null;
      var valTxt = hasMed ? fmtNum(r.ps.median) + ' tok/s' : '样本不足';
      var samp = hasMed ? '速度 ' + r.ps.n + ' 条 / ' + r.ps.votes + ' 票'
        : (r.ps.n ? '速度 ' + r.ps.n + ' 条（&lt;5）' : '无速度样本');
      return '<div class="cmp-stat"><span class="med">' + esc(valTxt) + '</span>'
        + '<span class="cnt">总 ' + r.n + ' 条 · ' + samp + '</span>'
        + '<span class="sent">满意 ' + r.sent.satisfied + ' · 褒贬 ' + r.sent.mixed + ' · 后悔 ' + r.sent.regret + '</span></div>';
    }
    var bars = allRows.map(function (r) {
      var hasMed = r.ps.median !== null;
      var pct = hasMed ? Math.max(2, r.ps.median / maxMed * 100) : 0;
      var valTxt = hasMed ? fmtNum(r.ps.median) + ' tok/s' : '样本不足';
      var inside = pct > 34;
      var bar = '<div class="bar-track"><div class="bar-fill' + (hasMed ? '' : ' dim') + (r.cat === '多卡/多机' ? ' multi' : '') + '" style="width:' + pct.toFixed(1) + '%">'
        + (hasMed && inside ? '<span class="bar-val">' + esc(valTxt) + '</span>' : '') + '</div></div>';
      return '<div class="cmp-row">'
        + '<div class="cmp-name">' + catBadge(r.cat) + '<span class="sub">' + esc(r.machines.join('，') || '—') + '</span></div>'
        + bar + statBlock(r) + '</div>';
    }).join('');

    var tbl = '<div class="tbl-scroll"><table class="tbl"><thead><tr>'
      + '<th>机器类别</th><th class="num">实测数</th><th class="num">速度样本</th><th class="num">中位数 tok/s</th><th class="num">区间</th><th>态度（满/褒/后）</th></tr></thead><tbody>'
      + allRows.map(function (r) {
        var med = r.ps.median !== null ? fmtNum(r.ps.median) : '<span class="na">样本不足</span>';
        var range = r.ps.median !== null ? fmtNum(r.ps.min) + '–' + fmtNum(r.ps.max) : '<span class="na">—</span>';
        var samp = r.ps.n + ' 条 / ' + r.ps.votes + ' 票';
        return '<tr><td data-label="类别">' + catBadge(r.cat) + '</td>'
          + '<td class="num" data-label="实测数">' + r.n + '</td>'
          + '<td class="num" data-label="速度样本">' + samp + '</td>'
          + '<td class="num" data-label="中位数">' + med + '</td>'
          + '<td class="num" data-label="区间">' + range + '</td>'
          + '<td data-label="态度">' + r.sent.satisfied + ' / ' + r.sent.mixed + ' / ' + r.sent.regret + '</td></tr>';
      }).join('') + '</tbody></table></div>';

    root.innerHTML = '<div class="controls">'
      + '<div class="field"><label>选择模型（在同一模型上比较）</label><select data-k="model">' + modelOptions(model) + '</select></div>'
      + '<div class="spacer"></div>'
      + '<button class="btn" data-act="to-model">查看该模型全部实测 →</button>'
      + '</div>'
      + '<p class="lede">固定模型 <strong>' + esc(model) + '</strong>，把各类机器并排比。显卡按 <strong>N 卡 / A 卡</strong> 分开；'
      + '多卡/多机（如 2× RTX 3090、两台 DGX Spark）单独成行，不并进单卡。'
      + '因为只比同一个模型，MoE 与稠密的速度差异不会算到机器头上。中位数按「每人每机器每模型一票」，样本少于 5 条不给中位数。</p>'
      + (subset.length ? '<div class="compare-grid">'
        + '<div class="cmp-row head"><div>机器类别 / 代表机型</div><div>单流生成速度中位数（tok/s）</div><div style="text-align:right">总数 / 速度样本 / 态度</div></div>'
        + bars + '</div>'
        + '<p class="cmp-note">该模型全部实测合计 ' + subset.length + ' 条'
        + (overall.median !== null ? '，单卡总体中位数 ' + fmtNum(overall.median) + ' tok/s（' + overall.votes + ' 票）' : '，单卡总体样本不足 5 条不给中位数')
        + (multiRow ? '；多卡/多机 ' + multi.length + ' 条单列' : '')
        + (uncat ? '；另有 ' + uncat + ' 条单卡未注明机器类别，未计入上图。' : '。') + '</p>'
        + tbl
        : '<div class="empty">该模型暂无亲测记录。</div>');
    bindControls(root, s, commit);
    var btn = root.querySelector('[data-act="to-model"]');
    if (btn) btn.addEventListener('click', function () { s.view = 'model'; s.model = model; commit(s); });
  }

  /* ---------- 视图：第一问 机器→能跑什么 ---------- */
  function machineOptions(selected, cat) {
    var pool = cat ? STAT.filter(function (r) { return r.machine_category === cat; }) : STAT;
    var counts = sortedEntries(countBy(pool, 'machine_canon'));
    return '<option value="">— 选择机器 —</option>' + counts.map(function (e) {
      var c = machineCat(e[0]);
      return '<option value="' + esc(e[0]) + '"' + (selected === e[0] ? ' selected' : '') + '>' + esc(e[0]) + (c ? ' [' + esc(c) + ']' : '') + '（' + e[1] + '）</option>';
    }).join('');
  }
  function renderMachine(root, s) {
    var catOpts = '<option value="">全部类别</option>' + CATS.map(function (c) {
      return '<option value="' + esc(c) + '"' + (s.cat === c ? ' selected' : '') + '>' + esc(c) + '</option>';
    }).join('');
    var head = '<div class="controls">'
      + '<div class="field"><label>按类别缩小</label><select data-k="cat">' + catOpts + '</select></div>'
      + '<div class="field"><label>选择你的机器</label><select data-k="machine">' + machineOptions(s.machine, s.cat) + '</select></div>'
      + '</div>';
    if (!s.machine) {
      var top = sortedEntries(countBy(STAT, 'machine_canon')).slice(0, 12);
      var picker = '<div class="picker">' + top.map(function (e) {
        return '<button class="pick" data-machine="' + esc(e[0]) + '"><span class="pn">' + esc(e[0]) + '</span>'
          + '<span class="pm">' + catBadge(machineCat(e[0])) + '<span>' + e[1] + ' 条实测</span></span></button>';
      }).join('') + '</div>';
      root.innerHTML = head + '<p class="lede">选一台机器，看网友在它上面跑过哪些模型、各自多快、满意还是后悔。下面是实测最多的机器：</p>' + picker;
      bindControls(root, s, commit);
      root.querySelectorAll('[data-machine]').forEach(function (b) {
        b.addEventListener('click', function () { s.machine = b.getAttribute('data-machine'); commit(s); });
      });
      return;
    }
    var rs = STAT.filter(function (r) { return r.machine_canon === s.machine; });
    var cat = machineCat(s.machine);
    var byModel = {};
    rs.forEach(function (r) { var k = r.model_canon || '（模型未指明）'; (byModel[k] = byModel[k] || []).push(r); });
    var modelRows = Object.keys(byModel).map(function (k) { return { model: k, rs: byModel[k], ps: personStats(byModel[k]), sent: sentimentCounts(byModel[k]) }; })
      .sort(function (a, b) { return b.rs.length - a.rs.length; });
    var tbl = '<div class="tbl-scroll"><table class="tbl"><thead><tr>'
      + '<th>模型</th><th class="num">实测数</th><th class="num">中位数 tok/s</th><th class="num">区间</th><th>态度（满/褒/后）</th></tr></thead><tbody>'
      + modelRows.map(function (m) {
        var med = m.ps.median !== null ? fmtNum(m.ps.median) : '<span class="na">样本不足</span>';
        var range = m.ps.median !== null ? fmtNum(m.ps.min) + '–' + fmtNum(m.ps.max) : '<span class="na">—</span>';
        return '<tr class="clickable" data-model="' + esc(m.model) + '"><td class="name" data-label="模型">' + esc(m.model) + '</td>'
          + '<td class="num" data-label="实测数">' + m.rs.length + '</td>'
          + '<td class="num" data-label="中位数">' + med + '</td>'
          + '<td class="num" data-label="区间">' + range + '</td>'
          + '<td data-label="态度">' + m.sent.satisfied + ' / ' + m.sent.mixed + ' / ' + m.sent.regret + '</td></tr>';
      }).join('') + '</tbody></table></div>';
    root.innerHTML = head
      + '<div class="sec-h"><span class="no">Q1</span><h2>' + esc(s.machine) + '</h2>' + catBadge(cat) + '<span class="sub">' + rs.length + ' 条亲测</span></div>'
      + '<p class="lede">这台机器跑过的模型如下（点任一行可在「第二问」里看该模型需要什么机器）。每行一个模型，中位数不跨模型混算。</p>'
      + tbl + '<div id="cards"></div>';
    bindControls(root, s, commit);
    root.querySelectorAll('tr[data-model]').forEach(function (tr) {
      tr.addEventListener('click', function () { s.view = 'model'; s.model = tr.getAttribute('data-model'); commit(s); });
    });
    renderCards(root.querySelector('#cards'), rs, s, { showCat: false, sync: cardSync });
  }

  /* ---------- 视图：第二问 模型→要什么机器 ---------- */
  function renderModel(root, s) {
    var model = s.model || META.default_compare_model;
    var rs = STAT.filter(function (r) { return r.model_canon === model; });
    var byMachine = {};
    rs.forEach(function (r) { var k = r.machine_canon || '（机器未指明）'; (byMachine[k] = byMachine[k] || []).push(r); });
    var rows = Object.keys(byMachine).map(function (k) {
      return { machine: k, cat: machineCat(k), rs: byMachine[k], ps: personStats(byMachine[k]), sent: sentimentCounts(byMachine[k]) };
    }).sort(function (a, b) {
      var am = a.ps.median, bm = b.ps.median;
      if (am === null && bm === null) return b.rs.length - a.rs.length;
      if (am === null) return 1; if (bm === null) return -1;
      return bm - am;
    });
    var tbl = '<div class="tbl-scroll"><table class="tbl"><thead><tr>'
      + '<th>机器</th><th>类别</th><th class="num">实测数</th><th class="num">中位数 tok/s</th><th class="num">区间</th><th>态度（满/褒/后）</th></tr></thead><tbody>'
      + rows.map(function (m) {
        var med = m.ps.median !== null ? fmtNum(m.ps.median) : '<span class="na">样本不足</span>';
        var range = m.ps.median !== null ? fmtNum(m.ps.min) + '–' + fmtNum(m.ps.max) : '<span class="na">—</span>';
        return '<tr class="clickable" data-machine="' + esc(m.machine) + '"><td class="name" data-label="机器">' + esc(m.machine) + '</td>'
          + '<td data-label="类别">' + catBadge(m.cat) + '</td>'
          + '<td class="num" data-label="实测数">' + m.rs.length + '</td>'
          + '<td class="num" data-label="中位数">' + med + '</td>'
          + '<td class="num" data-label="区间">' + range + '</td>'
          + '<td data-label="态度">' + m.sent.satisfied + ' / ' + m.sent.mixed + ' / ' + m.sent.regret + '</td></tr>';
      }).join('') + '</tbody></table></div>';
    root.innerHTML = '<div class="controls">'
      + '<div class="field"><label>选择你想跑的模型</label><select data-k="model">' + modelOptions(model) + '</select></div>'
      + '<div class="spacer"></div><button class="btn" data-act="to-compare">在对比视图看这个模型 →</button>'
      + '</div>'
      + '<div class="sec-h"><span class="no">Q2</span><h2>' + esc(model) + '</h2><span class="sub">' + rs.length + ' 条亲测</span></div>'
      + '<p class="lede">跑这个模型，网友用过这些机器，按速度中位数排序（点任一行可在「第一问」里看那台机器还能跑什么）。样本少于 5 条不给中位数。</p>'
      + (rs.length ? tbl : '<div class="empty">该模型暂无亲测记录。</div>')
      + '<div id="cards"></div>';
    bindControls(root, s, commit);
    root.querySelectorAll('tr[data-machine]').forEach(function (tr) {
      tr.addEventListener('click', function () { s.view = 'machine'; s.machine = tr.getAttribute('data-machine'); commit(s); });
    });
    var btn = root.querySelector('[data-act="to-compare"]');
    if (btn) btn.addEventListener('click', function () { s.view = 'compare'; s.model = model; commit(s); });
    renderCards(root.querySelector('#cards'), rs, s, { showCat: true, sync: cardSync });
  }

  /* ---------- 口径说明 / 页脚 ---------- */
  function basisHTML() {
    var b = META.basis;
    return '<section class="section anchor-offset" id="basis"><div class="sec-h"><span class="no">§</span><h2>统计口径</h2></div>'
      + '<div class="basis"><dl>'
      + '<dt>计数</dt><dd>' + esc(b.count) + '</dd>'
      + '<dt>中位数</dt><dd>' + esc(b.median) + '</dd>'
      + '<dt>排除</dt><dd>' + esc(b.exclude) + '</dd>'
      + (b.supplement ? '<dt>补自上文</dt><dd>' + esc(b.supplement) + '</dd>' : '')
      + '<dt>声明</dt><dd>' + esc(b.disclaimer) + '</dd>'
      + '</dl></div></section>';
  }
  function kpiHTML() {
    var items = [
      [META.stat_records, '亲测·去重实测'],
      [META.speed_stat_records, '进入速度统计'],
      [META.distinct_machine, '机器（标准名）'],
      [META.distinct_model, '模型（标准名）'],
      [META.regret_fp_records, '后悔实测']
    ];
    return items.map(function (it) {
      return '<div class="kpi"><span class="n">' + it[0] + '</span><span class="l">' + esc(it[1]) + '</span></div>';
    }).join('');
  }
  function footerHTML() {
    return '<footer class="footer"><div class="wrap">'
      + '<span><strong>数据来源</strong>：' + esc(META.source) + '（许可 ' + esc(META.license) + '）</span>'
      + '<span><strong>时间范围</strong>：' + esc(META.range) + ' · 生成于 ' + esc(META.generated) + '</span>'
      + '<span><strong>样本</strong>：抽取 ' + META.total_records + ' 条，亲测 ' + META.fp_records + ' 条，去重后 ' + META.stat_records + ' 条进入计数，' + META.speed_stat_records + ' 条进入速度统计。</span>'
      + '<span>全部数据为 Hacker News 网友自述，非标准化基准测试，仅供参考。每条实测可点回 HN 原帖核对。</span>'
      + '</div></footer>';
  }

  /* ---------- 首页 ---------- */
  var INDEX_DEFAULTS = { view: 'compare', machine: '', model: '', cat: '', q: '', sent: '', sort: 'speed_desc', dups: false };
  // 各视图用到的参数；切视图时清掉无关参数（网址不留冗余）
  var VIEW_PARAMS = {
    compare: ['view', 'model'],
    machine: ['view', 'machine', 'cat', 'q', 'sent', 'sort', 'dups'],
    model: ['view', 'model', 'cat', 'q', 'sent', 'sort', 'dups']
  };
  function pruneForView(s) {
    var keep = VIEW_PARAMS[s.view] || VIEW_PARAMS.compare;
    Object.keys(INDEX_DEFAULTS).forEach(function (k) { if (keep.indexOf(k) < 0) s[k] = INDEX_DEFAULTS[k]; });
    return s;
  }
  var iState, iRoot;
  function cardSync(s) { writeState(pruneForView(s), INDEX_DEFAULTS); }  // 卡片筛选：只写网址，局部刷新
  function commit(s) { pruneForView(s); writeState(s, INDEX_DEFAULTS); renderIndex(); }
  function renderIndex() {
    document.querySelectorAll('.tab').forEach(function (t) { t.classList.toggle('active', t.getAttribute('data-view') === iState.view); });
    if (iState.view === 'machine') renderMachine(iRoot, iState);
    else if (iState.view === 'model') renderModel(iRoot, iState);
    else renderCompare(iRoot, iState);
  }
  function scrollToBasis() {
    var el = document.getElementById('basis');
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  function initIndex() {
    iRoot = document.getElementById('view-root');
    var kp = document.getElementById('kpis'); if (kp) kp.innerHTML = kpiHTML();
    iState = readState(INDEX_DEFAULTS);
    document.querySelectorAll('.tab').forEach(function (t) {
      t.addEventListener('click', function () { iState.view = t.getAttribute('data-view'); commit(iState); });
    });
    // 口径锚点：点击总是滚动到位（即便当前 hash 已是 #basis），不重置视图/筛选
    var basisLink = document.querySelector('.nav-links a[href="#basis"]');
    if (basisLink) basisLink.addEventListener('click', function (e) {
      e.preventDefault(); scrollToBasis();
      try { history.replaceState(null, '', location.pathname + '#basis'); } catch (_) { location.hash = 'basis'; }
    });
    window.addEventListener('hashchange', function () {
      var h = location.hash.replace(/^#/, '');
      if (h === 'basis') { scrollToBasis(); return; }  // 口径锚点：不重置视图/筛选
      if (applyingHash) { applyingHash = false; return; }
      iState = readState(INDEX_DEFAULTS); renderIndex();
    });
    renderIndex();
    if (location.hash.replace(/^#/, '') === 'basis') scrollToBasis();
  }

  /* ---------- 后悔页（筛选条稳定，搜索去抖局部刷新；小结含「机器未指明」加得拢总数） ---------- */
  var REGRET_DEFAULTS = { machine: '', cat: '', q: '', sort: 'speed_asc' };
  var rState, rRoot;
  function regretControlsHTML(s) {
    var machineOpts = '<option value="">全部机器</option>' + sortedEntries(countBy(REGRET, 'machine_canon')).map(function (e) {
      return '<option value="' + esc(e[0]) + '"' + (s.machine === e[0] ? ' selected' : '') + '>' + esc(e[0]) + '（' + e[1] + '）</option>';
    }).join('');
    var catOpts = '<option value="">全部类别</option>' + CATS.map(function (c) {
      return '<option value="' + esc(c) + '"' + (s.cat === c ? ' selected' : '') + '>' + esc(c) + '</option>';
    }).join('');
    var sortOpts = [['speed_asc', '速度从低到高'], ['speed_desc', '速度从高到低'], ['time_desc', '时间从新到旧']]
      .map(function (o) { return '<option value="' + o[0] + '"' + (s.sort === o[0] ? ' selected' : '') + '>' + o[1] + '</option>'; }).join('');
    return '<div class="controls">'
      + '<div class="field"><label>机器类别</label><select data-k="cat">' + catOpts + '</select></div>'
      + '<div class="field"><label>机器</label><select data-k="machine">' + machineOpts + '</select></div>'
      + '<div class="field"><label>排序</label><select data-k="sort">' + sortOpts + '</select></div>'
      + '<div class="field field-search"><label>搜索</label><input type="search" data-k="q" value="' + esc(s.q) + '" placeholder="机器/模型/摘要/作者"></div>'
      + '</div>';
  }
  function refreshRegret() {
    var pool = REGRET.slice();
    if (rState.cat) pool = pool.filter(function (r) { return r.machine_category === rState.cat; });
    if (rState.machine) pool = pool.filter(function (r) { return r.machine_canon === rState.machine; });
    if (rState.q) {
      var q = rState.q.toLowerCase();
      pool = pool.filter(function (r) {
        return [r.summary_zh, r.machine_canon, r.model_canon, r.by, (r.evidence_en || []).join(' ')].join(' ').toLowerCase().indexOf(q) >= 0;
      });
    }
    var groups = {};
    pool.forEach(function (r) { var k = r.machine_canon || '（机器未指明）'; (groups[k] = groups[k] || []).push(r); });
    var keys = Object.keys(groups).sort(function (a, b) { return groups[b].length - groups[a].length || a.localeCompare(b, 'zh'); });
    var sort = rState.sort || 'speed_asc';
    keys.forEach(function (k) {
      groups[k].sort(function (a, b) {
        if (sort === 'time_desc') return (b.time || '').localeCompare(a.time || '');
        var av = a.speed_value, bv = b.speed_value;
        if (av === null || av === undefined) av = Infinity; if (bv === null || bv === undefined) bv = Infinity;
        return sort === 'speed_desc' ? bv - av : av - bv;
      });
    });
    var body = keys.length ? keys.map(function (k) {
      var cat = machineCat(k);
      return '<div class="regret-group"><h3>' + esc(k) + ' ' + catBadge(cat) + '<span class="cnt">' + groups[k].length + ' 条后悔</span></h3>'
        + '<div class="cards">' + groups[k].map(cardHTML).join('') + '</div></div>';
    }).join('') : '<div class="empty">没有符合条件的后悔实测。</div>';
    var listEl = rRoot.querySelector('.regret-list');
    if (listEl) listEl.innerHTML = '<p class="result-count">显示 ' + pool.length + ' / ' + REGRET.length + ' 条后悔实测，按机器分组。</p>' + body;
    // 类别小结：按人算（每类实测人数/后悔人数/比例），合计按人去重；卡片仍全列
    var sumEl = document.getElementById('regret-summary');
    if (sumEl) sumEl.innerHTML = regretPersonSummary();
  }
  function initRegret() {
    rRoot = document.getElementById('regret-root');
    rState = readState(REGRET_DEFAULTS);
    rRoot.innerHTML = regretControlsHTML(rState) + '<div class="regret-list"></div>';
    function sync() { writeState(rState, REGRET_DEFAULTS); }
    rRoot.querySelectorAll('.controls [data-k]').forEach(function (el) {
      var k = el.getAttribute('data-k');
      if (el.type === 'search') {
        var dr = debounce(function () { sync(); refreshRegret(); }, 120);
        el.addEventListener('input', function () { rState.q = el.value; dr(); });
      } else {
        el.addEventListener('change', function () { rState[k] = el.value; sync(); refreshRegret(); });
      }
    });
    window.addEventListener('hashchange', function () {
      if (applyingHash) { applyingHash = false; return; }
      rState = readState(REGRET_DEFAULTS); syncControls(rRoot, rState); refreshRegret();
    });
    refreshRegret();
  }

  /* ---------- 启动 ---------- */
  function boot() {
    var page = document.body.getAttribute('data-page');
    var foot = document.getElementById('footer');
    if (foot) foot.outerHTML = footerHTML();
    if (page === 'regret') { initRegret(); }
    else {
      var basis = document.getElementById('basis-mount');
      if (basis) basis.outerHTML = basisHTML();
      initIndex();
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
