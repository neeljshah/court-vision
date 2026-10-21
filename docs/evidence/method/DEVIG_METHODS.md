# Method excerpt: de-vig methods and "the close"

Source (private path, line range, as of 626fe42f0):
- `src/prediction/devig.py`, lines 1-24 (module docstring), 54-63, 72-114, 117-136, 139-177,
  203-225 (`_METHODS` and the `devig` dispatcher)
- Public: `docs/papers/PREGAME_VS_CLOSE_2026.md` sections 2, 3.2 and 4.1;
  `scripts/platformkit/eval_gate/shin.py` (`shin_devig`)

All methods take implied probabilities pi_i = 1 / decimal price (summing to S > 1, the overround)
and return probabilities summing to 1.

## The methods in src/prediction/devig.py

| Function | Formula |
|---|---|
| `proportional_devig` (alias `additive`) | p_i = pi_i / S |
| `multiplicative_devig` | find k with sum_i pi_i^k = 1 (bisection); p_i = pi_i^k |
| `power_devig` | p_i = pi_i^(1/n) / sum_j pi_j^(1/n), n = number of outcomes by default |
| `shin_devig` (Shin 1992) | find z in [0, 1) with sum_i p_i(z) = 1 (bisection), formula below |

```python
    def p_of_z(z: float, q: float) -> float:
        return (math.sqrt(z * z + 4.0 * (1.0 - z) * q * q / s) - z) / (2.0 * (1.0 - z))
```

`multiplicative_devig`, `power_devig` and `shin_devig` fall back to `proportional_devig` on
degenerate input (non-positive prices; for Shin, an overround at or below one). The dispatcher
`devig(vigged, method="shin")` accepts `additive`, `proportional`, `multiplicative`, `power`,
`shin`. The public pregame figures are computed with the public `eval_gate/shin.py`, which raises
on a booksum below one instead of falling back; the private module is the engine's library copy.

## Which method the headline rows use (from the paper)

PREGAME_VS_CLOSE_2026.md section 3.2 states it directly:

> - **Proportional** (the primary rows): p_1 = imp_1 / (imp_1 + imp_2).
> - **Shin** (the sensitivity rows): Shin's insider-share model.

Section 4.1 reports the MLB moneyline and soccer O/U 2.5 rows with proportional de-vig. For NBA
moneyline it reports both; the row the verdict sentence cites is the Shin one, with the
proportional row beside it. Section 4.2 is the de-vig sensitivity table.

## What "the close" means there

Section 2 names the close per sport (quoted from the table):

> MLB: "closing moneyline, same archive" (sportsbookreviewsonline.com).
> Soccer: "Pinnacle closing O/U 2.5, via football-data.co.uk".
> NBA: "ESPN odds endpoint (ESPN BET, then DraftKings)".

All three are sportsbook closing prices from public archives, not exchange prices. There is no
project-side timestamp rule: the close is whatever the archive records as closing. For NBA the
paper adds that "the odds file has no snapshot timestamp", and that it is not established that the
cached price is the closing price. (In play, the reference is a Kalshi exchange price on the same
tick; see INGAME_VS_MARKET_2026.md. That is not "the close".)

## What it guarantees / what it does not

Guarantees: the formula behind each de-vig label is stated and checkable; the public Shin
implementation has a public test (`python -m pytest scripts/platformkit/eval_gate/test_shin.py -q`).
The headline rows name their method, and a second method is reported as a sensitivity check.

Does not guarantee: that any de-vig recovers the true probability (each is a model of how the
margin is spread). It does not make the NBA close timestamped, and it does not publish the private
multiplicative or power variants' use anywhere in the headline rows (they are not used there).
