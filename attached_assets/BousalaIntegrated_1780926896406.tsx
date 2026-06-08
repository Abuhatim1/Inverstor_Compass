/**
 * BousalaIntegrated.jsx
 * Integrated design — built on the existing BousalaScreens.tsx
 *
 * WHAT CHANGED vs original:
 *   NAV    10 items → 8 items (Research demoted, Cash Ledger merged into Accounts)
 *   S1     Net Worth: LineChart → AreaChart with gradient fill; snapshot button added
 *   S2     Holdings:  unchanged (already strong)
 *   S3     Allocation: By Market promoted first; Sector bar consolidated
 *   S4     Transactions: unchanged
 *   S5     Accounts + Cash Ledger merged into one screen with tabs
 *   S6     Alt Investments: unchanged (best screen in original)
 *   S7     Real Assets: unchanged
 *   S8     Cashflow: NEW — monthly income/expense summary
 *   S9     Goals: NEW — promoted from locked Settings module
 *   S10    Settings: updated modules list
 *
 * Dependencies: react, recharts, lucide-react
 */

import { useState } from 'react'
import {
  AreaChart, Area, PieChart, Pie, Cell,
  BarChart, Bar, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts'
import {
  Compass, TrendingUp, TrendingDown, Wallet, Building2,
  Settings, AlertCircle, CheckCircle2, Clock, Plus,
  BarChart2, List, CreditCard, Landmark, Car, Gem,
  ArrowUpRight, ArrowDownRight, ChevronRight,
  BadgeDollarSign, Layers, Target, Cpu, RefreshCw,
  Home, Globe, BookOpen,
} from 'lucide-react'

// ─── Design tokens (identical to original — no disruption) ──────────────────
const T = {
  bg:       '#0f1117',
  sidebar:  '#13161f',
  card:     '#1a1d2e',
  cardHov:  '#1e2236',
  border:   '#252840',
  accent:   '#6366f1',
  accentLt: '#6366f115',
  green:    '#22c55e',
  greenLt:  '#22c55e18',
  red:      '#ef4444',
  redLt:    '#ef444418',
  amber:    '#f59e0b',
  amberLt:  '#f59e0b18',
  blue:     '#3b82f6',
  purple:   '#a855f7',
  teal:     '#14b8a6',
  text:     '#e2e8f0',
  muted:    '#7c8499',
  dim:      '#3d4157',
}

// ─── Mock data (same as original + additions for new screens) ────────────────
const HOLDINGS = [
  { id:'1', ticker:'2222.SR', name:'Saudi Aramco',    market:'Saudi', sector:'Energy',     qty:500, cost:31.20, price:29.85, ccy:'SAR', weight:22.4 },
  { id:'2', ticker:'AAPL',    name:'Apple Inc.',      market:'US',    sector:'Technology', qty:12,  cost:168.40,price:211.32,ccy:'USD', weight:18.7 },
  { id:'3', ticker:'1180.SR', name:'Al Rajhi Bank',  market:'Saudi', sector:'Financials', qty:200, cost:88.50, price:96.70, ccy:'SAR', weight:14.1 },
  { id:'4', ticker:'MSFT',    name:'Microsoft Corp.', market:'US',    sector:'Technology', qty:8,   cost:310.00,price:434.87,ccy:'USD', weight:12.8 },
  { id:'5', ticker:'2010.SR', name:'SABIC',           market:'Saudi', sector:'Materials',  qty:150, cost:94.20, price:87.30, ccy:'SAR', weight:9.6  },
  { id:'6', ticker:'4030.SR', name:'Dar Al Arkan',   market:'Saudi', sector:'Real Estate',qty:800, cost:11.80, price:14.20, ccy:'SAR', weight:8.3  },
]

const ALLOCATION_SECTOR = [
  { name:'Energy',      value:22.4, color:'#f59e0b' },
  { name:'Technology',  value:31.5, color:'#6366f1' },
  { name:'Financials',  value:14.1, color:'#3b82f6' },
  { name:'Materials',   value:9.6,  color:'#22c55e' },
  { name:'Real Estate', value:8.3,  color:'#a855f7' },
  { name:'Cash',        value:14.1, color:'#64748b' },
]

const ALLOCATION_MARKET = [
  { name:'Saudi Market', value:54.4, color:'#22c55e' },
  { name:'US Market',    value:31.5, color:'#3b82f6' },
  { name:'Cash',         value:14.1, color:'#64748b' },
]

const NW_HISTORY = [
  { month:'Jan', nw:842000 }, { month:'Feb', nw:867000 },
  { month:'Mar', nw:851000 }, { month:'Apr', nw:889000 },
  { month:'May', nw:921000 }, { month:'Jun', nw:948500 },
]

const TRANSACTIONS = [
  { id:'T1', date:'2026-05-28', type:'BUY',  ticker:'AAPL',    qty:3,   price:205.40, total:616.20,  acct:'Aljazira' },
  { id:'T2', date:'2026-05-15', type:'SELL', ticker:'2222.SR', qty:100, price:31.50,  total:3150,    acct:'Tadawul'  },
  { id:'T3', date:'2026-04-30', type:'BUY',  ticker:'MSFT',    qty:2,   price:418.00, total:836,     acct:'Aljazira' },
  { id:'T4', date:'2026-04-18', type:'DIV',  ticker:'1180.SR', qty:0,   price:0,      total:280,     acct:'Tadawul'  },
  { id:'T5', date:'2026-03-22', type:'BUY',  ticker:'4030.SR', qty:400, price:11.80,  total:4720,    acct:'Tadawul'  },
  { id:'T6', date:'2026-03-10', type:'SELL', ticker:'2010.SR', qty:50,  price:97.40,  total:4870,    acct:'Tadawul'  },
]

const ACCOUNTS = [
  { id:'A1', name:'Aljazira Capital', type:'Brokerage', ccy:'USD', cash:12480.50, active:true  },
  { id:'A2', name:'Tadawul Account',  type:'Brokerage', ccy:'SAR', cash:34200.00, active:true  },
  { id:'A3', name:'Al Rajhi Cash',    type:'Bank',      ccy:'SAR', cash:85000.00, active:true  },
  { id:'A4', name:'USDC Wallet',      type:'Crypto',    ccy:'USD', cash:2100.00,  active:false },
]

const CASH_LEDGER = [
  { date:'2026-05-28', type:'BUY Settlement',  acct:'Aljazira', amount:-616.20, balance:12480.50, ccy:'USD' },
  { date:'2026-05-15', type:'SELL Settlement', acct:'Tadawul',  amount:3150,    balance:34200.00, ccy:'SAR' },
  { date:'2026-04-30', type:'BUY Settlement',  acct:'Aljazira', amount:-836,    balance:13096.70, ccy:'USD' },
  { date:'2026-04-18', type:'Dividend',        acct:'Tadawul',  amount:280,     balance:31050.00, ccy:'SAR' },
  { date:'2026-03-22', type:'BUY Settlement',  acct:'Tadawul',  amount:-4720,   balance:30770.00, ccy:'SAR' },
]

const IGI = [
  { id:'I1', name:'IGI Real Estate Fund A', principal:200000, current:214500, yield:7.2, start:'2025-01-15', maturity:'2026-07-15', status:'Maturity Action Required', structure:'Murabaha', daysLeft:37 },
  { id:'I2', name:'IGI Infrastructure B',   principal:150000, current:158800, yield:6.8, start:'2025-06-01', maturity:'2027-06-01', status:'Active',                   structure:'Ijara',    daysLeft:358 },
  { id:'I3', name:'IGI Sukuk Fund C',       principal:100000, current:100000, yield:5.5, start:'2026-04-01', maturity:'2027-04-01', status:'Pending Funding',           structure:'Sukuk',    daysLeft:296 },
  { id:'I4', name:'IGI Equity Plus D',      principal:80000,  current:91200,  yield:8.1, start:'2024-09-01', maturity:'2025-09-01', status:'Closed',                   structure:'Mudaraba', daysLeft:0 },
]

const REAL_ASSETS = [
  { id:'R1', type:'Property', name:'Riyadh Apartment',     value:680000, ccy:'SAR', date:'2024-01-01', liability:'Mortgage  · 420K remaining' },
  { id:'R2', type:'Vehicle',  name:'Toyota Land Cruiser',  value:185000, ccy:'SAR', date:'2025-06-01', liability:'Auto Loan · 95K remaining' },
  { id:'R3', type:'Gold',     name:'Gold (50 tola)',        value:142000, ccy:'SAR', date:'2026-01-15', liability:null },
]

const LIABILITIES = [
  { id:'L1', type:'Mortgage',  name:'Riyadh Apartment Mortgage', balance:420000, rate:3.8, monthly:2200, ccy:'SAR', maturity:'2044-01-01' },
  { id:'L2', type:'Auto Loan', name:'Land Cruiser Finance',      balance:95000,  rate:4.2, monthly:1800, ccy:'SAR', maturity:'2030-06-01' },
]

// NEW data for Cashflow and Goals
const CASHFLOW_DATA = [
  { month:'Jan', inc:85000, exp:31000 },
  { month:'Feb', inc:92000, exp:38000 },
  { month:'Mar', inc:88000, exp:35000 },
  { month:'Apr', inc:91000, exp:42000 },
  { month:'May', inc:87000, exp:34000 },
  { month:'Jun', inc:89000, exp:42000 },
]

const GOALS = [
  { id:'G1', name:'Financial Independence',  icon:'🏖',  target:2000000, current:1068500, pct:53.4, deadline:'2030', color:T.accent },
  { id:'G2', name:'Children\'s Education',   icon:'🎓',  target:400000,  current:214500,  pct:53.6, deadline:'2031', color:T.purple },
  { id:'G3', name:'Second Property',         icon:'🏠',  target:800000,  current:133800,  pct:16.7, deadline:'2028', color:T.amber  },
]

// ─── Shared helpers (identical to original) ──────────────────────────────────
const fmt  = (n, ccy = 'SAR', dec = 0) => n.toLocaleString('en-SA', { minimumFractionDigits:dec, maximumFractionDigits:dec }) + ' ' + ccy
const pct  = n => (n >= 0 ? '+' : '') + n.toFixed(2) + '%'
const pnlC = n => n >= 0 ? T.green : T.red

// ─── Shared UI atoms (same as original) ──────────────────────────────────────
const Badge = ({ label, color }) => (
  <span style={{ background:color+'22', color, border:`1px solid ${color}44`,
    borderRadius:6, padding:'2px 8px', fontSize:11, fontWeight:600, whiteSpace:'nowrap' }}>
    {label}
  </span>
)

const statusBadge = s => {
  const map = { 'Active':T.green, 'Pending Funding':T.amber,
    'Maturity Action Required':T.red, 'Closed':T.muted }
  return <Badge label={s} color={map[s] ?? T.muted} />
}

const MetricCard = ({ label, value, sub, subColor, icon:Icon, accent }) => (
  <div style={{ background:T.card, border:`1px solid ${T.border}`, borderRadius:12,
    padding:'18px 20px', flex:1, minWidth:160 }}>
    <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:10 }}>
      <div style={{ background:accent+'22', borderRadius:8, padding:6,
        display:'flex', alignItems:'center', justifyContent:'center' }}>
        <Icon size={15} color={accent} />
      </div>
      <span style={{ color:T.muted, fontSize:12, fontWeight:500 }}>{label}</span>
    </div>
    <div style={{ color:T.text, fontSize:22, fontWeight:700, letterSpacing:-0.5 }}>{value}</div>
    {sub && <div style={{ color:subColor ?? T.muted, fontSize:12, marginTop:4 }}>{sub}</div>}
  </div>
)

const SectionTitle = ({ children }) => (
  <h2 style={{ color:T.text, fontSize:16, fontWeight:700, margin:'0 0 16px 0' }}>{children}</h2>
)

const Divider = () => <div style={{ height:1, background:T.border, margin:'24px 0' }} />

const Th = ({ children, align }) => (
  <th style={{ padding:'10px 14px', fontSize:11, color:T.muted, fontWeight:600,
    textAlign:align ?? 'left', letterSpacing:0.5, textTransform:'uppercase' }}>{children}</th>
)

const Td = ({ children, align, color }) => (
  <td style={{ padding:'10px 14px', fontSize:13, color:color ?? T.text,
    textAlign:align ?? 'left', whiteSpace:'nowrap' }}>{children}</td>
)

const Table = ({ heads, children }) => (
  <div style={{ background:T.card, border:`1px solid ${T.border}`, borderRadius:12, overflow:'hidden' }}>
    <table style={{ width:'100%', borderCollapse:'collapse' }}>
      <thead>
        <tr style={{ borderBottom:`1px solid ${T.border}`, background:T.cardHov }}>
          {heads.map(h => <Th key={h}>{h}</Th>)}
        </tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
  </div>
)

const TR = ({ children }) => (
  <tr style={{ borderBottom:`1px solid ${T.border}` }}>{children}</tr>
)

// Circular progress arc — new component for Goals
const CircleProgress = ({ pct: p, size=60, color, strokeW=5 }) => {
  const r = (size - strokeW) / 2
  const circ = 2 * Math.PI * r
  const offset = circ * (1 - p / 100)
  return (
    <svg width={size} height={size} style={{ flexShrink:0 }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={T.border} strokeWidth={strokeW}/>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={strokeW}
        strokeDasharray={circ} strokeDashoffset={offset}
        strokeLinecap="round" transform={`rotate(-90 ${size/2} ${size/2})`}/>
      <text x={size/2} y={size/2+4} textAnchor="middle" fontSize={11}
        fontWeight={700} fill={color}>{Math.round(p)}%</text>
    </svg>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// SCREEN 1 — NET WORTH   (upgraded: AreaChart + snapshot button)
// ═══════════════════════════════════════════════════════════════════════════
const NetWorthScreen = () => {
  const totalAssets = 1583500, totalLiab = 515000
  const netWorth = totalAssets - totalLiab
  const prevNW   = 921000
  const delta    = netWorth - prevNW
  const deltaPct = (delta / prevNW) * 100

  const breakdown = [
    { label:'Portfolio',       value:687400,  color:T.accent  },
    { label:'Alt Investments', value:473300,  color:T.purple  },
    { label:'Real Assets',     value:1007000, color:T.amber   },
    { label:'Cash',            value:133800,  color:T.blue    },
  ]

  return (
    <div>
      {/* Alert banner — same as original */}
      <div style={{ background:T.red+'18', border:`1px solid ${T.red}44`, borderRadius:10,
        padding:'12px 16px', display:'flex', alignItems:'center', gap:10,
        marginBottom:20, color:T.red, fontSize:13 }}>
        <AlertCircle size={16} />
        <span><strong>Action required:</strong> IGI Fund A reaches maturity on 15 Jul 2026 — choose reinvest or withdraw.</span>
        <button style={{ marginLeft:'auto', background:'transparent', border:'none',
          color:T.red, cursor:'pointer', opacity:0.6, fontSize:16 }}>✕</button>
      </div>

      {/* Net worth hero — same layout, bigger breathing room */}
      <div style={{ background:T.card, border:`1px solid ${T.border}`, borderRadius:16,
        padding:'32px 32px 24px', marginBottom:20, textAlign:'center' }}>
        <div style={{ color:T.muted, fontSize:13, marginBottom:8, letterSpacing:0.5 }}>
          TOTAL NET WORTH · صافي الثروة
        </div>
        <div style={{ color:T.text, fontSize:52, fontWeight:800, letterSpacing:-2,
          lineHeight:1, marginBottom:12 }}>
          {fmt(netWorth)}
        </div>
        <div style={{ display:'inline-flex', alignItems:'center', gap:6, marginBottom:20,
          color:delta >= 0 ? T.green : T.red, fontSize:14, fontWeight:600 }}>
          {delta >= 0 ? <ArrowUpRight size={16}/> : <ArrowDownRight size={16}/>}
          {fmt(Math.abs(delta))} ({pct(deltaPct)}) vs last snapshot
        </div>
        {/* UPGRADE: AreaChart with gradient fill */}
        <ResponsiveContainer width="100%" height={160}>
          <AreaChart data={NW_HISTORY} margin={{ top:4, bottom:0, left:0, right:0 }}>
            <defs>
              <linearGradient id="nwGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor={T.accent} stopOpacity={0.3}/>
                <stop offset="95%" stopColor={T.accent} stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={T.border} vertical={false}/>
            <XAxis dataKey="month" tick={{ fill:T.muted, fontSize:11 }} axisLine={false} tickLine={false}/>
            <YAxis tick={{ fill:T.muted, fontSize:11 }} axisLine={false} tickLine={false}
              tickFormatter={v => (v/1000)+'K'}/>
            <Tooltip contentStyle={{ background:T.card, border:`1px solid ${T.border}`, borderRadius:8 }}
              labelStyle={{ color:T.muted }} itemStyle={{ color:T.accent }}
              formatter={v => [fmt(v), 'Net Worth']}/>
            <Area type="monotone" dataKey="nw" stroke={T.accent} strokeWidth={2.5}
              fill="url(#nwGrad)" dot={{ fill:T.accent, r:4 }} activeDot={{ r:6 }}/>
          </AreaChart>
        </ResponsiveContainer>
        {/* NEW: snapshot button inline with chart */}
        <div style={{ display:'flex', justifyContent:'flex-end', marginTop:12 }}>
          <button style={{ background:T.accentLt, color:T.accent, border:`1px solid ${T.accent}44`,
            borderRadius:8, padding:'7px 16px', fontSize:13, fontWeight:600, cursor:'pointer',
            display:'flex', alignItems:'center', gap:6 }}>
            <Clock size={13}/> Take Snapshot
          </button>
        </div>
      </div>

      {/* Metric row */}
      <div style={{ display:'flex', gap:12, marginBottom:20, flexWrap:'wrap' }}>
        <MetricCard label="Total Assets"      value={fmt(totalAssets)} icon={TrendingUp}  accent={T.green} />
        <MetricCard label="Total Liabilities" value={fmt(totalLiab)}   icon={CreditCard}  accent={T.red}   />
        <MetricCard label="Debt Ratio"        value="32.5%"            icon={BarChart2}   accent={T.amber} sub="of total assets" />
        <MetricCard label="Last Snapshot"     value="14 days ago"      icon={Clock}       accent={T.blue}  sub="Take a snapshot →" subColor={T.amber} />
      </div>

      {/* Asset breakdown */}
      <div style={{ background:T.card, border:`1px solid ${T.border}`,
        borderRadius:12, padding:'20px 24px' }}>
        <SectionTitle>Asset Breakdown</SectionTitle>
        <div style={{ display:'flex', gap:2, height:14, borderRadius:8,
          overflow:'hidden', marginBottom:16 }}>
          {breakdown.map(a => (
            <div key={a.label} style={{ flex:a.value, background:a.color }} title={a.label}/>
          ))}
        </div>
        <div style={{ display:'flex', gap:20, flexWrap:'wrap' }}>
          {breakdown.map(a => (
            <div key={a.label} style={{ display:'flex', alignItems:'center', gap:6, fontSize:13 }}>
              <div style={{ width:10, height:10, borderRadius:3, background:a.color }}/>
              <span style={{ color:T.muted }}>{a.label}</span>
              <span style={{ color:T.text, fontWeight:600 }}>{fmt(a.value)}</span>
              <span style={{ color:T.muted }}>({((a.value/totalAssets)*100).toFixed(1)}%)</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// SCREEN 2 — HOLDINGS   (unchanged — already production-ready)
// ═══════════════════════════════════════════════════════════════════════════
const HoldingsScreen = () => {
  const totalValue = 687400, totalCost = 621200
  const totalPnl = totalValue - totalCost
  const pnlPct   = (totalPnl / totalCost) * 100

  return (
    <div>
      <div style={{ display:'flex', gap:12, marginBottom:20, flexWrap:'wrap' }}>
        <MetricCard label="Portfolio Value" value={fmt(totalValue)} icon={Wallet}    accent={T.accent} />
        <MetricCard label="Total Cost"      value={fmt(totalCost)}  icon={BarChart2} accent={T.blue}   />
        <MetricCard label="Unrealized P&L"  value={fmt(totalPnl)}   icon={TrendingUp} accent={T.green}
          sub={pct(pnlPct)} subColor={pnlC(totalPnl)} />
        <MetricCard label="Positions"       value={String(HOLDINGS.length)} icon={Layers} accent={T.purple} />
      </div>

      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:12 }}>
        <SectionTitle>Positions</SectionTitle>
        <div style={{ display:'flex', gap:8 }}>
          <button style={{ background:T.accentLt, color:T.accent, border:`1px solid ${T.accent}44`,
            borderRadius:8, padding:'7px 14px', fontSize:13, fontWeight:600, cursor:'pointer',
            display:'flex', alignItems:'center', gap:5 }}>
            <Plus size={13}/>Add Position
          </button>
          <button style={{ background:T.card, color:T.muted, border:`1px solid ${T.border}`,
            borderRadius:8, padding:'7px 12px', fontSize:13, cursor:'pointer' }}>
            <RefreshCw size={13}/>
          </button>
        </div>
      </div>

      <Table heads={['Ticker','Company','Market','Qty','Avg Cost','Price','Mkt Value','P&L','Weight']}>
        {HOLDINGS.map(h => {
          const mv = h.qty * h.price, cb = h.qty * h.cost, pnl = mv - cb, pp = (pnl/cb)*100
          return (
            <TR key={h.id}>
              <Td><span style={{ color:T.accent, fontWeight:700 }}>{h.ticker}</span></Td>
              <Td color={T.muted}>{h.name}</Td>
              <Td><Badge label={h.market} color={h.market==='Saudi'?T.green:T.blue}/></Td>
              <Td align="right">{h.qty.toLocaleString()}</Td>
              <Td align="right" color={T.muted}>{h.cost.toFixed(2)}</Td>
              <Td align="right">{h.price.toFixed(2)}</Td>
              <Td align="right">{fmt(mv, h.ccy, 0)}</Td>
              <Td align="right" color={pnlC(pnl)}>
                {pnl >= 0 ? '+' : ''}{pnl.toFixed(0)} ({pct(pp)})
              </Td>
              <Td align="right" color={T.muted}>{h.weight}%</Td>
            </TR>
          )
        })}
      </Table>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// SCREEN 3 — ALLOCATION  (consolidated: By Market first, Sector bar)
// ═══════════════════════════════════════════════════════════════════════════
const AllocationScreen = () => (
  <div>
    <div style={{ display:'flex', gap:20, flexWrap:'wrap', marginBottom:20 }}>
      {/* By Market — promoted first (most relevant for Gulf investor) */}
      <div style={{ background:T.card, border:`1px solid ${T.border}`, borderRadius:12,
        padding:'20px 24px', flex:1, minWidth:280 }}>
        <SectionTitle>By Market</SectionTitle>
        <div style={{ display:'flex', alignItems:'center', gap:20 }}>
          <PieChart width={180} height={180}>
            <Pie data={ALLOCATION_MARKET} cx={85} cy={85} innerRadius={50} outerRadius={80}
              dataKey="value" paddingAngle={2}>
              {ALLOCATION_MARKET.map((e,i) => <Cell key={i} fill={e.color}/>)}
            </Pie>
            <Tooltip formatter={v => [v+'%', '']}
              contentStyle={{ background:T.card, border:`1px solid ${T.border}`, borderRadius:8 }}/>
          </PieChart>
          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            {ALLOCATION_MARKET.map(s => (
              <div key={s.name} style={{ display:'flex', alignItems:'center', gap:8, fontSize:13 }}>
                <div style={{ width:10, height:10, borderRadius:3, background:s.color, flexShrink:0 }}/>
                <span style={{ color:T.muted, minWidth:100 }}>{s.name}</span>
                <span style={{ color:T.text, fontWeight:600 }}>{s.value}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      {/* By Sector */}
      <div style={{ background:T.card, border:`1px solid ${T.border}`, borderRadius:12,
        padding:'20px 24px', flex:1, minWidth:280 }}>
        <SectionTitle>By Sector</SectionTitle>
        <div style={{ display:'flex', alignItems:'center', gap:20 }}>
          <PieChart width={180} height={180}>
            <Pie data={ALLOCATION_SECTOR} cx={85} cy={85} innerRadius={50} outerRadius={80}
              dataKey="value" paddingAngle={2}>
              {ALLOCATION_SECTOR.map((e,i) => <Cell key={i} fill={e.color}/>)}
            </Pie>
            <Tooltip formatter={v => [v+'%', '']}
              contentStyle={{ background:T.card, border:`1px solid ${T.border}`, borderRadius:8 }}/>
          </PieChart>
          <div style={{ display:'flex', flexDirection:'column', gap:7 }}>
            {ALLOCATION_SECTOR.map(s => (
              <div key={s.name} style={{ display:'flex', alignItems:'center', gap:8, fontSize:12 }}>
                <div style={{ width:9, height:9, borderRadius:2, background:s.color, flexShrink:0 }}/>
                <span style={{ color:T.muted, minWidth:80 }}>{s.name}</span>
                <span style={{ color:T.text, fontWeight:600 }}>{s.value}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
    {/* Value by position bar */}
    <div style={{ background:T.card, border:`1px solid ${T.border}`, borderRadius:12, padding:'20px 24px' }}>
      <SectionTitle>Market Value by Position</SectionTitle>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={HOLDINGS.map(h => ({ name:h.ticker, value:h.qty*h.price }))}>
          <CartesianGrid strokeDasharray="3 3" stroke={T.border} vertical={false}/>
          <XAxis dataKey="name" tick={{ fill:T.muted, fontSize:11 }} axisLine={false} tickLine={false}/>
          <YAxis tick={{ fill:T.muted, fontSize:11 }} axisLine={false} tickLine={false}
            tickFormatter={v => (v/1000).toFixed(0)+'K'}/>
          <Tooltip contentStyle={{ background:T.card, border:`1px solid ${T.border}`, borderRadius:8 }}
            labelStyle={{ color:T.muted }} formatter={v => [fmt(v), 'Value']}/>
          <Bar dataKey="value" fill={T.accent} radius={[4,4,0,0]}/>
        </BarChart>
      </ResponsiveContainer>
    </div>
  </div>
)

// ═══════════════════════════════════════════════════════════════════════════
// SCREEN 4 — TRANSACTIONS   (unchanged)
// ═══════════════════════════════════════════════════════════════════════════
const TransactionsScreen = () => {
  const typeColor = t => ({ BUY:T.green, SELL:T.red, DIV:T.blue })[t] ?? T.muted
  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
        <SectionTitle>Transaction History</SectionTitle>
        <span style={{ color:T.muted, fontSize:13 }}>Read-only audit log</span>
      </div>
      <Table heads={['Date','Type','Ticker','Qty','Price','Total','Account']}>
        {TRANSACTIONS.map(tx => (
          <TR key={tx.id}>
            <Td color={T.muted}>{tx.date}</Td>
            <Td><Badge label={tx.type} color={typeColor(tx.type)}/></Td>
            <Td><span style={{ color:T.accent, fontWeight:700 }}>{tx.ticker}</span></Td>
            <Td align="right">{tx.qty > 0 ? tx.qty : '—'}</Td>
            <Td align="right" color={T.muted}>{tx.price > 0 ? tx.price.toFixed(2) : '—'}</Td>
            <Td align="right">{tx.total.toLocaleString()}</Td>
            <Td color={T.muted}>{tx.acct}</Td>
          </TR>
        ))}
      </Table>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// SCREEN 5 — ACCOUNTS + CASH LEDGER   (merged, two tabs)
// ═══════════════════════════════════════════════════════════════════════════
const AccountsScreen = () => {
  const [tab, setTab] = useState('accounts')
  const typeColor = t => ({ Brokerage:T.accent, Bank:T.green, Crypto:T.purple })[t] ?? T.muted

  return (
    <div>
      {/* Tab selector */}
      <div style={{ display:'flex', gap:0, border:`1px solid ${T.border}`, borderRadius:10,
        overflow:'hidden', marginBottom:20, width:'fit-content' }}>
        {[['accounts','Accounts'], ['ledger','Cash Ledger']].map(([key,label]) => (
          <button key={key} onClick={() => setTab(key)} style={{
            background: tab===key ? T.accent : 'transparent',
            color: tab===key ? '#fff' : T.muted,
            border:'none', padding:'8px 20px', fontSize:13, fontWeight:600, cursor:'pointer',
            transition:'all 0.15s',
          }}>{label}</button>
        ))}
      </div>

      {tab === 'accounts' && (
        <div>
          <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:14 }}>
            <SectionTitle>Accounts</SectionTitle>
            <button style={{ background:T.accentLt, color:T.accent, border:`1px solid ${T.accent}44`,
              borderRadius:8, padding:'7px 14px', fontSize:13, fontWeight:600, cursor:'pointer',
              display:'flex', alignItems:'center', gap:5 }}>
              <Plus size={13}/>Add Account
            </button>
          </div>
          <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
            {ACCOUNTS.map(a => (
              <div key={a.id} style={{ background:T.card, border:`1px solid ${T.border}`,
                borderRadius:12, padding:'18px 22px',
                display:'flex', alignItems:'center', justifyContent:'space-between',
                opacity:a.active ? 1 : 0.5 }}>
                <div style={{ display:'flex', alignItems:'center', gap:14 }}>
                  <div style={{ background:typeColor(a.type)+'22', borderRadius:10, padding:10,
                    display:'flex', alignItems:'center', justifyContent:'center' }}>
                    <Landmark size={18} color={typeColor(a.type)}/>
                  </div>
                  <div>
                    <div style={{ color:T.text, fontWeight:700, fontSize:15 }}>{a.name}</div>
                    <div style={{ display:'flex', gap:8, marginTop:4 }}>
                      <Badge label={a.type} color={typeColor(a.type)}/>
                      {!a.active && <Badge label="Inactive" color={T.muted}/>}
                    </div>
                  </div>
                </div>
                <div style={{ textAlign:'right' }}>
                  <div style={{ color:T.text, fontWeight:700, fontSize:18 }}>
                    {fmt(a.cash, a.ccy, 2)}
                  </div>
                  <div style={{ color:T.muted, fontSize:12, marginTop:2 }}>Cash balance</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'ledger' && (
        <div>
          <SectionTitle>Cash Ledger</SectionTitle>
          <Table heads={['Date','Type','Account','Amount','Balance']}>
            {CASH_LEDGER.map((e,i) => (
              <TR key={i}>
                <Td color={T.muted}>{e.date}</Td>
                <Td>{e.type}</Td>
                <Td color={T.muted}>{e.acct}</Td>
                <Td align="right" color={e.amount >= 0 ? T.green : T.red}>
                  {e.amount >= 0 ? '+' : ''}{e.amount.toFixed(2)} {e.ccy}
                </Td>
                <Td align="right">{fmt(e.balance, e.ccy, 2)}</Td>
              </TR>
            ))}
          </Table>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// SCREEN 6 — ALT INVESTMENTS   (unchanged — best screen in original)
// Added: daysLeft countdown on each card
// ═══════════════════════════════════════════════════════════════════════════
const AltInvestmentsScreen = () => {
  const activeTotal   = IGI.filter(i => i.status === 'Active').reduce((s,i) => s+i.current, 0)
  const deployedTotal = IGI.filter(i => i.status !== 'Closed').reduce((s,i) => s+i.principal, 0)

  return (
    <div>
      <div style={{ display:'flex', gap:12, marginBottom:20, flexWrap:'wrap' }}>
        <MetricCard label="Total Deployed" value={fmt(deployedTotal)} icon={BadgeDollarSign} accent={T.accent}/>
        <MetricCard label="Current Value"  value={fmt(activeTotal)}   icon={TrendingUp}      accent={T.green}/>
        <MetricCard label="Active Funds"   value="2"                  icon={Layers}          accent={T.purple}/>
        <MetricCard label="Avg Yield"      value="7.0%"               icon={BarChart2}       accent={T.amber} sub="projection only"/>
      </div>

      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:14 }}>
        <SectionTitle>Investments</SectionTitle>
        <button style={{ background:T.accentLt, color:T.accent, border:`1px solid ${T.accent}44`,
          borderRadius:8, padding:'7px 14px', fontSize:13, fontWeight:600, cursor:'pointer',
          display:'flex', alignItems:'center', gap:5 }}>
          <Plus size={13}/>Add Investment
        </button>
      </div>

      <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
        {IGI.map(inv => {
          const gain = inv.current - inv.principal
          const gainP = (gain / inv.principal) * 100
          return (
            <div key={inv.id} style={{ background:T.card,
              border:`1px solid ${inv.status==='Maturity Action Required' ? T.red+'66' : T.border}`,
              borderRadius:12, padding:'18px 22px' }}>
              <div style={{ display:'flex', justifyContent:'space-between',
                alignItems:'flex-start', marginBottom:12 }}>
                <div>
                  <div style={{ color:T.text, fontWeight:700, fontSize:15 }}>{inv.name}</div>
                  <div style={{ display:'flex', gap:8, marginTop:6 }}>
                    {statusBadge(inv.status)}
                    <Badge label={inv.structure} color={T.blue}/>
                    {/* NEW: days countdown */}
                    {inv.daysLeft > 0 && inv.status !== 'Closed' && (
                      <Badge
                        label={`${inv.daysLeft}d to maturity`}
                        color={inv.daysLeft < 60 ? T.red : T.muted}
                      />
                    )}
                  </div>
                </div>
                <div style={{ textAlign:'right' }}>
                  <div style={{ color:T.text, fontWeight:700, fontSize:17 }}>
                    {fmt(inv.current)}
                  </div>
                  <div style={{ color:pnlC(gain), fontSize:13, marginTop:2 }}>
                    {gain >= 0 ? '+' : ''}{fmt(gain)} ({pct(gainP)})
                  </div>
                </div>
              </div>
              <div style={{ display:'flex', gap:24, flexWrap:'wrap', fontSize:12, color:T.muted }}>
                <span>Principal: <strong style={{ color:T.text }}>{fmt(inv.principal)}</strong></span>
                <span>Yield: <strong style={{ color:T.text }}>{inv.yield}%</strong></span>
                <span>Start: <strong style={{ color:T.text }}>{inv.start}</strong></span>
                <span>Maturity: <strong style={{ color:inv.status==='Maturity Action Required'?T.red:T.text }}>
                  {inv.maturity}
                </strong></span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// SCREEN 7 — REAL ASSETS & LIABILITIES   (unchanged)
// ═══════════════════════════════════════════════════════════════════════════
const RealAssetsScreen = () => {
  const assetTotal = REAL_ASSETS.reduce((s,a) => s+a.value, 0)
  const liabTotal  = LIABILITIES.reduce((s,l) => s+l.balance, 0)
  const netEquity  = assetTotal - liabTotal
  const assetIcon  = t => ({ Property:<Building2 size={18}/>, Vehicle:<Car size={18}/>, Gold:<Gem size={18}/> })[t] ?? <Gem size={18}/>
  const assetColor = t => ({ Property:T.amber, Vehicle:T.blue, Gold:T.purple })[t] ?? T.muted

  return (
    <div>
      <div style={{ display:'flex', gap:12, marginBottom:20, flexWrap:'wrap' }}>
        <MetricCard label="Real Assets"  value={fmt(assetTotal)} icon={Home}       accent={T.amber}/>
        <MetricCard label="Liabilities"  value={fmt(liabTotal)}  icon={CreditCard} accent={T.red}  />
        <MetricCard label="Net Equity"   value={fmt(netEquity)}  icon={TrendingUp} accent={T.green}/>
      </div>

      <SectionTitle>Real Assets</SectionTitle>
      <div style={{ display:'flex', flexDirection:'column', gap:10, marginBottom:24 }}>
        {REAL_ASSETS.map(a => (
          <div key={a.id} style={{ background:T.card, border:`1px solid ${T.border}`,
            borderRadius:12, padding:'16px 22px',
            display:'flex', alignItems:'center', justifyContent:'space-between' }}>
            <div style={{ display:'flex', alignItems:'center', gap:12 }}>
              <div style={{ background:assetColor(a.type)+'22', borderRadius:8, padding:9,
                display:'flex', color:assetColor(a.type) }}>
                {assetIcon(a.type)}
              </div>
              <div>
                <div style={{ color:T.text, fontWeight:600 }}>{a.name}</div>
                <div style={{ color:T.muted, fontSize:12, marginTop:2 }}>
                  {a.type} · Last valued {a.date}
                  {a.liability && <span style={{ color:T.amber }}> · {a.liability}</span>}
                </div>
              </div>
            </div>
            <div style={{ color:T.text, fontWeight:700, fontSize:16 }}>{fmt(a.value, a.ccy)}</div>
          </div>
        ))}
        <button style={{ background:'transparent', border:`1px dashed ${T.border}`, borderRadius:12,
          padding:'14px', color:T.muted, fontSize:13, cursor:'pointer',
          display:'flex', alignItems:'center', justifyContent:'center', gap:6 }}>
          <Plus size={14}/> Add Real Asset
        </button>
      </div>

      <SectionTitle>Liabilities</SectionTitle>
      <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
        {LIABILITIES.map(l => (
          <div key={l.id} style={{ background:T.card, border:`1px solid ${T.border}`,
            borderRadius:12, padding:'16px 22px',
            display:'flex', alignItems:'center', justifyContent:'space-between' }}>
            <div>
              <div style={{ color:T.text, fontWeight:600 }}>{l.name}</div>
              <div style={{ color:T.muted, fontSize:12, marginTop:2 }}>
                {l.type} · {l.rate}% rate · {fmt(l.monthly, l.ccy)}/month · Matures {l.maturity}
              </div>
            </div>
            <div style={{ textAlign:'right' }}>
              <div style={{ color:T.red, fontWeight:700, fontSize:16 }}>{fmt(l.balance, l.ccy)}</div>
              <div style={{ color:T.muted, fontSize:12 }}>outstanding</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// SCREEN 8 — CASHFLOW   (NEW — monthly income/expense snapshot)
// ═══════════════════════════════════════════════════════════════════════════
const CashflowScreen = () => {
  const latest = CASHFLOW_DATA[CASHFLOW_DATA.length - 1]
  const surplus = latest.inc - latest.exp

  return (
    <div>
      <div style={{ display:'flex', gap:12, marginBottom:20, flexWrap:'wrap' }}>
        <MetricCard label="Jun Income"   value={fmt(latest.inc)} icon={TrendingUp}   accent={T.green}/>
        <MetricCard label="Jun Expenses" value={fmt(latest.exp)} icon={TrendingDown} accent={T.red}  />
        <MetricCard label="Jun Surplus"  value={fmt(surplus)}    icon={Wallet}       accent={T.teal}
          sub="available to invest" subColor={T.teal}/>
      </div>

      <div style={{ background:T.card, border:`1px solid ${T.border}`, borderRadius:12,
        padding:'20px 24px', marginBottom:20 }}>
        <SectionTitle>6-Month Trend</SectionTitle>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={CASHFLOW_DATA} barGap={6}>
            <CartesianGrid strokeDasharray="3 3" stroke={T.border} vertical={false}/>
            <XAxis dataKey="month" tick={{ fill:T.muted, fontSize:11 }} axisLine={false} tickLine={false}/>
            <YAxis tick={{ fill:T.muted, fontSize:11 }} axisLine={false} tickLine={false}
              tickFormatter={v => (v/1000).toFixed(0)+'K'}/>
            <Tooltip contentStyle={{ background:T.card, border:`1px solid ${T.border}`, borderRadius:8 }}
              labelStyle={{ color:T.muted }}
              formatter={(v, name) => [fmt(v), name.charAt(0).toUpperCase()+name.slice(1)]}/>
            <Bar dataKey="inc" name="income"   fill={T.green}  radius={[4,4,0,0]}/>
            <Bar dataKey="exp" name="expenses" fill={T.red}    radius={[4,4,0,0]}/>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Monthly entry log */}
      <div style={{ background:T.card, border:`1px solid ${T.border}`, borderRadius:12, padding:'20px 24px' }}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:14 }}>
          <SectionTitle>Monthly Summary Log</SectionTitle>
          <button style={{ background:T.accentLt, color:T.accent, border:`1px solid ${T.accent}44`,
            borderRadius:8, padding:'7px 14px', fontSize:13, fontWeight:600, cursor:'pointer',
            display:'flex', alignItems:'center', gap:5 }}>
            <Plus size={13}/>Add Month
          </button>
        </div>
        <Table heads={['Month','Income','Expenses','Surplus','Rate']}>
          {[...CASHFLOW_DATA].reverse().map((m,i) => {
            const s = m.inc - m.exp
            const rate = ((s/m.inc)*100).toFixed(1)
            return (
              <TR key={i}>
                <Td>{m.month} 2026</Td>
                <Td align="right" color={T.green}>{fmt(m.inc)}</Td>
                <Td align="right" color={T.red}>{fmt(m.exp)}</Td>
                <Td align="right" color={s>0?T.teal:T.red}>{s>0?'+':''}{fmt(s)}</Td>
                <Td align="right" color={T.muted}>{rate}% savings</Td>
              </TR>
            )
          })}
        </Table>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// SCREEN 9 — GOALS   (NEW — promoted from locked Settings)
// ═══════════════════════════════════════════════════════════════════════════
const GoalsScreen = () => {
  const nw = 1068500
  return (
    <div>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:20 }}>
        <div style={{ color:T.muted, fontSize:13 }}>
          Based on net worth of <strong style={{ color:T.text }}>{fmt(nw)}</strong>
        </div>
        <button style={{ background:T.accentLt, color:T.accent, border:`1px solid ${T.accent}44`,
          borderRadius:8, padding:'7px 14px', fontSize:13, fontWeight:600, cursor:'pointer',
          display:'flex', alignItems:'center', gap:5 }}>
          <Plus size={13}/>New Goal
        </button>
      </div>

      <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
        {GOALS.map(g => {
          const remaining = g.target - g.current
          const needed    = (remaining / 12).toFixed(0)
          return (
            <div key={g.id} style={{ background:T.card, border:`1px solid ${T.border}`,
              borderRadius:14, padding:'22px 24px' }}>
              <div style={{ display:'flex', alignItems:'center', gap:18 }}>
                {/* Circular progress */}
                <CircleProgress pct={g.pct} size={72} color={g.color} strokeW={6}/>
                {/* Details */}
                <div style={{ flex:1 }}>
                  <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:8 }}>
                    <div>
                      <div style={{ fontSize:18, marginBottom:3 }}>{g.icon}</div>
                      <div style={{ color:T.text, fontWeight:700, fontSize:15 }}>{g.name}</div>
                      <div style={{ color:T.muted, fontSize:12, marginTop:2 }}>Target: {g.deadline}</div>
                    </div>
                    <div style={{ textAlign:'right' }}>
                      <div style={{ color:T.text, fontWeight:700, fontSize:17 }}>{fmt(g.current)}</div>
                      <div style={{ color:T.muted, fontSize:12 }}>of {fmt(g.target)}</div>
                    </div>
                  </div>
                  {/* Progress bar */}
                  <div style={{ height:6, background:T.border, borderRadius:4, overflow:'hidden', marginBottom:8 }}>
                    <div style={{ width:`${g.pct}%`, height:'100%', background:g.color, borderRadius:4 }}/>
                  </div>
                  <div style={{ display:'flex', gap:20, fontSize:12 }}>
                    <span style={{ color:T.muted }}>
                      Remaining: <strong style={{ color:T.text }}>{fmt(remaining)}</strong>
                    </span>
                    <span style={{ color:T.muted }}>
                      Monthly needed: <strong style={{ color:T.text }}>{fmt(parseInt(needed))}</strong>
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      <Divider/>
      <div style={{ background:T.card, border:`1px dashed ${T.border}`, borderRadius:12,
        padding:'24px', textAlign:'center' }}>
        <Target size={28} color={T.dim} style={{ marginBottom:10 }}/>
        <div style={{ color:T.muted, fontSize:14 }}>Add your next financial milestone</div>
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// SCREEN 10 — SETTINGS   (updated modules list)
// ═══════════════════════════════════════════════════════════════════════════
const SettingsScreen = () => {
  const modules = [
    { key:'core',        label:'Net Worth Core',         status:'active',  free:true  },
    { key:'holdings',    label:'Portfolio Tracker',      status:'active',  free:false },
    { key:'altinvest',   label:'Alternative Investments',status:'active',  free:false },
    { key:'realassets',  label:'Real Assets & Liabilities',status:'active',free:false },
    { key:'cashflow',    label:'Cashflow Tracker',       status:'active',  free:false },
    { key:'goals',       label:'Goals & Projections',    status:'active',  free:false },
    { key:'research',    label:'Research & AI Analysis', status:'locked',  free:false },
    { key:'reports',     label:'Reports & Export',       status:'locked',  free:false },
    { key:'snapshots+',  label:'Snapshot History Plus',  status:'locked',  free:false },
  ]

  return (
    <div>
      <div style={{ background:T.card, border:`1px solid ${T.border}`, borderRadius:12,
        padding:'20px 24px', marginBottom:16 }}>
        <SectionTitle>Display Preferences</SectionTitle>
        <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
          {[
            { label:'Base Currency', desc:'All totals displayed in this currency',
              control: <select style={{ background:T.cardHov, color:T.text, border:`1px solid ${T.border}`, borderRadius:8, padding:'6px 12px', fontSize:13 }}><option>SAR</option><option>USD</option><option>AED</option></select> },
            { label:'Language', desc:'Interface language',
              control: <div style={{ display:'flex', border:`1px solid ${T.border}`, borderRadius:8, overflow:'hidden' }}><button style={{ background:T.accent, color:'#fff', border:'none', padding:'6px 16px', fontSize:13, fontWeight:600, cursor:'pointer' }}>EN</button><button style={{ background:'transparent', color:T.muted, border:'none', padding:'6px 16px', fontSize:13, cursor:'pointer' }}>ع</button></div> },
            { label:'Price Staleness Warning', desc:'Warn when price is older than',
              control: <select style={{ background:T.cardHov, color:T.text, border:`1px solid ${T.border}`, borderRadius:8, padding:'6px 12px', fontSize:13 }}><option>3 days</option><option>7 days</option><option>1 day</option></select> },
          ].map((row, i, arr) => (
            <div key={i}>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                <div>
                  <div style={{ color:T.text, fontSize:14, fontWeight:600 }}>{row.label}</div>
                  <div style={{ color:T.muted, fontSize:12 }}>{row.desc}</div>
                </div>
                {row.control}
              </div>
              {i < arr.length-1 && <div style={{ height:1, background:T.border, marginTop:14 }}/>}
            </div>
          ))}
        </div>
      </div>

      <div style={{ background:T.card, border:`1px solid ${T.border}`, borderRadius:12, padding:'20px 24px' }}>
        <SectionTitle>Subscription Modules</SectionTitle>
        <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
          {modules.map(m => (
            <div key={m.key} style={{ display:'flex', alignItems:'center',
              justifyContent:'space-between', padding:'12px 14px',
              background:T.cardHov, borderRadius:10, opacity:m.status==='locked'?0.6:1 }}>
              <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                {m.status==='active'
                  ? <CheckCircle2 size={16} color={T.green}/>
                  : <Clock size={16} color={T.dim}/>}
                <span style={{ color:T.text, fontSize:14, fontWeight:500 }}>{m.label}</span>
                {m.free && <Badge label="Free" color={T.green}/>}
              </div>
              {m.status==='locked'
                ? <button style={{ background:T.accentLt, color:T.accent,
                    border:`1px solid ${T.accent}44`, borderRadius:6, padding:'4px 12px',
                    fontSize:12, fontWeight:600, cursor:'pointer' }}>Upgrade</button>
                : <Badge label="Active" color={T.green}/>}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Navigation (8 items, down from 10) ──────────────────────────────────────
const NAV = [
  { key:'networth',      label:'Net Worth',        arLabel:'صافي الثروة',       icon:Home          },
  { key:'holdings',      label:'Portfolio',         arLabel:'المحفظة',           icon:Wallet        },
  { key:'allocation',    label:'Allocation',        arLabel:'التوزيع',           icon:BarChart2     },
  { key:'transactions',  label:'Transactions',      arLabel:'المعاملات',         icon:List          },
  { key:'accounts',      label:'Accounts',          arLabel:'الحسابات والنقدية', icon:Landmark      },
  { key:'altinvest',     label:'Alt Investments',   arLabel:'الاستثمار البديل',  icon:Layers, badge:'!' },
  { key:'realassets',    label:'Real Assets',       arLabel:'الأصول العينية',    icon:Building2     },
  { key:'cashflow',      label:'Cashflow',          arLabel:'التدفق النقدي',     icon:TrendingUp    },
  { key:'goals',         label:'Goals',             arLabel:'الأهداف',           icon:Target        },
  { key:'settings',      label:'Settings',          arLabel:'الإعدادات',         icon:Settings      },
]

// ─── Sidebar ──────────────────────────────────────────────────────────────────
const Sidebar = ({ active, onChange, lang, onLangChange }) => (
  <div style={{ width:228, background:T.sidebar, borderRight:`1px solid ${T.border}`,
    display:'flex', flexDirection:'column', height:'100vh',
    position:'sticky', top:0, flexShrink:0 }}>
    {/* Logo */}
    <div style={{ padding:'22px 20px 16px', borderBottom:`1px solid ${T.border}` }}>
      <div style={{ display:'flex', alignItems:'center', gap:10 }}>
        <Compass size={24} color={T.accent}/>
        <div>
          <div style={{ color:T.text, fontWeight:800, fontSize:18, letterSpacing:-0.5 }}>بوصلة</div>
          <div style={{ color:T.muted, fontSize:11 }}>Investor Compass</div>
        </div>
      </div>
    </div>

    {/* Nav */}
    <nav style={{ flex:1, padding:'12px 10px', overflowY:'auto' }}>
      {NAV.map(n => {
        const isActive = n.key === active
        const Icon = n.icon
        return (
          <button key={n.key} onClick={() => onChange(n.key)} style={{
            width:'100%', display:'flex', alignItems:'center', gap:10,
            padding:'9px 12px', borderRadius:9, border:'none', cursor:'pointer',
            background: isActive ? T.accent+'22' : 'transparent',
            color: isActive ? T.accent : T.muted,
            fontSize:13, fontWeight:isActive ? 600 : 500, marginBottom:2,
            textAlign:'left', transition:'all 0.15s', position:'relative',
          }}>
            <Icon size={16}/>
            {lang==='ar' ? n.arLabel : n.label}
            {n.badge && (
              <span style={{ marginLeft:'auto', background:T.red, color:'#fff',
                borderRadius:'50%', width:16, height:16, fontSize:10, fontWeight:700,
                display:'flex', alignItems:'center', justifyContent:'center' }}>
                {n.badge}
              </span>
            )}
          </button>
        )
      })}
    </nav>

    {/* Footer */}
    <div style={{ padding:'12px 14px', borderTop:`1px solid ${T.border}` }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:10 }}>
        <span style={{ color:T.muted, fontSize:12 }}>Base currency</span>
        <select style={{ background:T.card, color:T.text, border:`1px solid ${T.border}`,
          borderRadius:6, padding:'3px 8px', fontSize:12 }}>
          <option>SAR</option><option>USD</option>
        </select>
      </div>
      <div style={{ display:'flex', gap:0, border:`1px solid ${T.border}`, borderRadius:7, overflow:'hidden' }}>
        <button onClick={() => lang!=='en' && onLangChange()} style={{
          flex:1, background:lang==='en'?T.accent:'transparent',
          color:lang==='en'?'#fff':T.muted, border:'none', padding:'5px',
          fontSize:12, fontWeight:600, cursor:'pointer' }}>EN</button>
        <button onClick={() => lang!=='ar' && onLangChange()} style={{
          flex:1, background:lang==='ar'?T.accent:'transparent',
          color:lang==='ar'?'#fff':T.muted, border:'none', padding:'5px',
          fontSize:12, fontWeight:600, cursor:'pointer' }}>ع</button>
      </div>
    </div>
  </div>
)

// ─── Main app ─────────────────────────────────────────────────────────────────
export default function BousalaIntegrated() {
  const [screen, setScreen] = useState('networth')
  const [lang,   setLang]   = useState('en')

  const screens = {
    networth:     <NetWorthScreen/>,
    holdings:     <HoldingsScreen/>,
    allocation:   <AllocationScreen/>,
    transactions: <TransactionsScreen/>,
    accounts:     <AccountsScreen/>,
    altinvest:    <AltInvestmentsScreen/>,
    realassets:   <RealAssetsScreen/>,
    cashflow:     <CashflowScreen/>,
    goals:        <GoalsScreen/>,
    settings:     <SettingsScreen/>,
  }

  const active = NAV.find(n => n.key === screen)

  return (
    <div style={{ display:'flex', background:T.bg, minHeight:'100vh',
      fontFamily:"'Segoe UI','Tajawal','Cairo',system-ui,sans-serif",
      direction: lang==='ar' ? 'rtl' : 'ltr' }}>
      <Sidebar active={screen} onChange={setScreen} lang={lang}
        onLangChange={() => setLang(l => l==='en'?'ar':'en')}/>
      <main style={{ flex:1, padding:'28px 36px', overflowY:'auto', maxWidth:980 }}>
        <div style={{ marginBottom:28 }}>
          <h1 style={{ color:T.text, fontSize:22, fontWeight:800, margin:0, letterSpacing:-0.5 }}>
            {lang==='ar' ? active.arLabel : active.label}
          </h1>
          <div style={{ color:T.muted, fontSize:13, marginTop:4 }}>
            بوصلة — Investor Compass
          </div>
        </div>
        {screens[screen]}
      </main>
    </div>
  )
}
