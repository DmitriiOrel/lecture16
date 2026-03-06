# Final ML-RL Model Spec (NEAR Spot + Perp Hedge)

## 1) Instruments and cadence
- Spot: `NEAR-USDT`
- Futures: `NEARUSDTM` (`m = 0.1 NEAR/contract`)
- Cycle: `15m` candles, rebalance each `15m`

## 2) ML layer
- Return forecast: `ARIMA` on spot log-returns `r_t = ln(S_t / S_{t-1})`
- Vol forecast: `GARCH(1,1)` on same return series

Output:
- `ret_hat_t`
- `sigma_hat_t`

## 3) Target construction
Definitions:
- `S_t`: spot price
- `N_max`: max spot notional per side (USDT)
- `eps`: numerical floor
- `z_max`: z-score clip

Formulas:
\[
z_t = clip\left(\frac{ret\_hat_t}{sigma\_hat_t + eps}, -z_{max}, z_{max}\right)
\]
\[
N_t = z_t \cdot N_{max}
\]
\[
q_t^{raw} = \frac{N_t}{S_t}
\]
\[
n_t = round\left(\frac{q_t^{raw}}{m}\right)
\]
\[
q_t^{target} = n_t \cdot m,\qquad c_t^{target} = -n_t
\]

This keeps hedge legs aligned to futures contract granularity.

## 4) RL controller
Agent controls futures adjustment in contracts:
\[
\Delta c_t \in \{-2,-1,0,+1,+2\}
\]
\[
c_t = clip(c_{t-1} + \Delta c_t,\ -C_{max}, C_{max})
\]
Spot target remains from ML (`q_t^{target}`), RL decides hedge timing/intensity.

## 5) Reward
\[
PnL_t = q_{t-1}(S_t-S_{t-1}) + (c_{t-1}m)(F_t-F_{t-1})
\]
\[
R_t = PnL_t - fee_t - slippage_t + funding_t
- \lambda_{turn}|c_t-c_{t-1}|
- \lambda_{\Delta}|(q_t + c_tm)S_t|
- \lambda_{dd}\max(0,DD_t-DD_{soft})^2
\]

## 6) Risk checks
- Gross notional:
\[
|q_t|S_t + |c_t|mF_t \le max\_gross\_notional
\]
- Single order notional:
\[
notional_{order} \le max\_single\_order
\]
- Futures leverage:
\[
\frac{|c_t|mF_t}{Equity_t} \le max\_futures\_leverage
\]
- Hard net-delta:
\[
|(q_t + c_tm)S_t| \le hard\_net\_delta\_limit
\]

## 7) Execution
- Market orders
- Chunking by `max_single_order_notional_usdt`
- Retry with bounded attempts
- `shadow` mode first, then `live`
