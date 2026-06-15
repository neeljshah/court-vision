"""EfficiencyCurves — Tennis: aggression-error frontiers and risk-reward curves.

Person-free, calibration-only, no edge/ROI/pick language.
"""
from __future__ import annotations

SPORT = "Tennis"
FAMILY = "EfficiencyCurves"

CONCEPTS: list[dict] = [
    {
        "slug": "aggression_error_tradeoff_curve",
        "title": "Aggression-Error Tradeoff Curve",
        "summary": (
            "Describes the frontier between rally-ball aggression intent and unforced-error rate, "
            "tracing how winner frequency rises then plateaus as shot pace and target depth increase "
            "while unforced errors accelerate past a threshold aggression band."
        ),
        "stat_signature": (
            "Winner rate (WN%) and unforced-error rate (UE%) as a function of average stroke "
            "pace tier; marginal WN% gain per +5 km/h averages +1.2 pp on hard courts but "
            "marginal UE% rises +2.1 pp past the 80th-percentile pace band."
        ),
        "mechanism": (
            "Faster, deeper strokes compress opponent reaction time and push contacts defensive, "
            "but they simultaneously shrink the hitter's own margin above the net and toward "
            "sidelines, creating a concave net-point-win curve that peaks and then inverts."
        ),
        "conditions": (
            "Most pronounced on slow clay where bounce amplifies pace differentials; curve "
            "shifts leftward (lower optimal pace) on slow surfaces and rightward on fast hard "
            "courts where lower-trajectory balls carry naturally."
        ),
        "magnitude": (
            "Crossing the efficient aggression band into the over-aggressive tail correlates "
            "with a 4-7 pp drop in points-won relative to the curve's peak, equivalent in "
            "magnitude to a mid-tier serve speed disadvantage across an entire set."
        ),
        "links": [
            "winner_to_error_efficient_frontier",
            "risk_reward_inflection_aggression",
            "surface_aggression_payoff_shift",
            "spin_pace_control_tradeoff",
        ],
    },
    {
        "slug": "winner_to_error_efficient_frontier",
        "title": "Winner-to-Error Efficient Frontier",
        "summary": (
            "The convex boundary mapping the maximum achievable (winners minus unforced errors) "
            "per point across the full aggression spectrum; aggression settings off this boundary "
            "are dominated by some other setting that yields both fewer errors and more winners."
        ),
        "stat_signature": (
            "Net point contribution = (WN - UE) / total points played; frontier is the upper "
            "envelope across aggression clusters; average frontier WN-UE ratio ~0.28-0.34 on "
            "hard courts versus 0.18-0.24 on clay for aggressive baseline archetypes."
        ),
        "mechanism": (
            "The frontier arises because winners and errors share the same shot-selection "
            "distribution; randomizing over shots off the frontier wastes margin by generating "
            "errors without the compensating winners that justified the risk."
        ),
        "conditions": (
            "Observable when rally data are segmented by aggression proxy (e.g., average ball "
            "speed or court-position depth at contact); most stable on surfaces with consistent "
            "pace and bounce; collapses to noise in short samples below ~200 rallies."
        ),
        "magnitude": (
            "The gap between a tour-typical player on-frontier versus 15 percentiles off-frontier "
            "in the over-aggressive direction averages 3-5 pp in points-won, compounding to a "
            "meaningful expected set-margin shift over 100 points."
        ),
        "links": [
            "aggression_error_tradeoff_curve",
            "risk_reward_inflection_aggression",
            "first_strike_versus_attrition_efficiency",
            "high_leverage_aggression_regression",
        ],
    },
    {
        "slug": "risk_reward_inflection_aggression",
        "title": "Risk-Reward Inflection in Aggression",
        "summary": (
            "The identifiable aggression level at which marginal unforced errors begin to "
            "outpace marginal winners — the derivative of (winners minus errors) with respect "
            "to aggression intent crosses zero and turns negative."
        ),
        "stat_signature": (
            "Inflection detectable when the rolling slope of UE% with respect to pace-band "
            "exceeds the slope of WN% across consecutive pace quintiles; typically occurs "
            "between the 70th and 85th pace-percentile band on hard courts."
        ),
        "mechanism": (
            "Beyond the inflection, the geometrical margin constraints (net clearance and court "
            "width) become binding: to add pace or depth the hitter must sacrifice so much "
            "margin that the distribution of landing zones crosses into net or wide at a rate "
            "that dominates the added time-pressure on the opponent."
        ),
        "conditions": (
            "Inflection point shifts with surface pace, ball type, and wind; high-altitude "
            "venues push the inflection rightward (more pace sustainable); heavy humid balls "
            "push it leftward. Second-ball contexts set a lower inflection than first-ball."
        ),
        "magnitude": (
            "The cost of ignoring the inflection and operating 10 pace-percentiles past it is "
            "typically 5-9 pp in unforced-error rate, producing a net swing of 4-7 pp in "
            "points-won that accumulates to multi-game swings within a set."
        ),
        "links": [
            "aggression_error_tradeoff_curve",
            "winner_to_error_efficient_frontier",
            "margin_compression_under_pressure_curve",
            "fatigue_aggression_sustainability_curve",
        ],
    },
    {
        "slug": "first_serve_pace_in_rate_tradeoff",
        "title": "First-Serve Pace-to-In-Rate Tradeoff",
        "summary": (
            "Traces how adding first-serve pace decreases first-serve-in percentage and the "
            "pace level that maximises expected first-serve points won, integrating both "
            "the direct ace/service-winner gain and the second-serve exposure cost."
        ),
        "stat_signature": (
            "First-serve in-rate drops approximately 1.5-2.5 pp per additional 10 km/h above "
            "the 75th-percentile pace band; optimal pace for points-won is typically 10-18 km/h "
            "below max pace for body-serve placements, 5-10 km/h below max for wide T targets."
        ),
        "mechanism": (
            "Faster deliveries gain time-compression benefit on the return but require tighter "
            "trajectory bands to clear the net at high angles; the intersection of margin loss "
            "and time-pressure gain determines the optimal pace — a well-defined peak in "
            "expected first-serve points won."
        ),
        "conditions": (
            "Tradeoff steepens in wet or heavy conditions where balls sit up and serve speed "
            "advantage is diluted; flattens at high altitude where the ball travels faster for "
            "the same racket speed. Wider service boxes on clay reduce net-height constraint slightly."
        ),
        "magnitude": (
            "Serving at max pace versus optimal pace typically costs 3-6 pp in first-serve "
            "points won; across a match this translates to 2-4 points per set directly attributable "
            "to pace-versus-placement miscalibration."
        ),
        "links": [
            "second_serve_aggression_double_fault_curve",
            "serve_plus_one_aggression_curve",
            "aggression_error_tradeoff_curve",
        ],
    },
    {
        "slug": "second_serve_aggression_double_fault_curve",
        "title": "Second-Serve Aggression Double-Fault Curve",
        "summary": (
            "Captures the tradeoff between increasing second-serve aggression — via pace, "
            "placement variety, or reduced spin — and the accelerating double-fault risk "
            "that erodes free-point concession to zero."
        ),
        "stat_signature": (
            "Double-fault rate rises from ~2-3% at conservative spin-heavy second serves to "
            "5-8% when second-serve pace exceeds the 70th percentile of first-serve pace; "
            "second-serve points won peaks around the 55th-65th pace percentile with heavy kick."
        ),
        "mechanism": (
            "The second serve requires a net-clearance margin and a landing-zone depth that "
            "together constrain pace far more than the first; adding pace on a kick serve "
            "primarily increases spin-rpm demand, and above a racket-speed threshold, ball "
            "flight variability exceeds reliable margin control."
        ),
        "conditions": (
            "Penalty for over-aggression on second serves steepens under fatigue and at "
            "high-leverage moments where anxiety-driven swing changes widen the distribution "
            "of contact quality; wet balls and heavy conditions amplify the cost further."
        ),
        "magnitude": (
            "Each additional double fault concedes a free point worth ~0.7-1.0 game-win "
            "probability in average leverage; across a match, three added double faults "
            "from over-aggression represents a measurable fraction of expected set margin."
        ),
        "links": [
            "first_serve_pace_in_rate_tradeoff",
            "second_serve_return_attack_efficiency",
            "risk_reward_inflection_aggression",
            "margin_compression_under_pressure_curve",
        ],
    },
    {
        "slug": "rally_tolerance_consistency_curve",
        "title": "Rally-Tolerance Consistency Curve",
        "summary": (
            "Describes how point-win efficiency changes as rally-length tolerance increases, "
            "tracing the net benefit of extending exchanges against the compounding unforced-error "
            "hazard per additional stroke."
        ),
        "stat_signature": (
            "Points won in rally-length brackets: 1-3 strokes, 4-8, 9+; unforced-error hazard "
            "per stroke rises from ~1-2% in short exchanges to 3-5% in 9+ stroke rallies; "
            "baseline consistency players show a flatter hazard curve at the cost of fewer winners."
        ),
        "mechanism": (
            "Each additional stroke in a rally is an independent error-exposure event; a player "
            "tolerating longer rallies either owns a flat hazard curve (true consistency) or "
            "accumulates mounting margin-fatigue per stroke. The crossover between "
            "a retriever's flat hazard and an aggressor's falling winner-rate determines the "
            "efficient rally-length regime for each archetype."
        ),
        "conditions": (
            "Tolerance curve is most analytically separable on clay, where rally length is "
            "naturally extended; on fast surfaces, rallies rarely reach the regime where the "
            "hazard difference between archetypes is observable."
        ),
        "magnitude": (
            "Archetypes with genuine flat hazard curves gain 2-4 pp in points-won specifically "
            "in the 9+ stroke regime versus those whose hazard rises steeply, representing the "
            "core consistency-versus-aggression outcome split."
        ),
        "links": [
            "first_strike_versus_attrition_efficiency",
            "court_position_aggression_payoff",
            "fatigue_aggression_sustainability_curve",
            "spin_pace_control_tradeoff",
        ],
    },
    {
        "slug": "court_position_aggression_payoff",
        "title": "Court-Position Aggression Payoff Curve",
        "summary": (
            "Traces how the return on aggressive shotmaking varies with court position at "
            "contact, quantifying the winner-minus-error differential per aggression unit "
            "from inside-the-baseline contacts relative to deep-defensive contact points."
        ),
        "stat_signature": (
            "Winner rate from inside the baseline: 18-28%; from behind the baseline: 5-11%; "
            "unforced-error rate rises 6-10 pp when attempting equivalent aggression from deep "
            "defensive positions versus mid-court contacts."
        ),
        "mechanism": (
            "Court position at contact determines available angle, net-crossing height, and "
            "ball-travel distance to landing zone; inside-baseline contacts allow lower net "
            "trajectories and wider angles simultaneously, steepening the payoff curve and "
            "shifting the aggression inflection rightward."
        ),
        "conditions": (
            "Payoff differential is largest on slow courts where positioning is earned through "
            "extended patterns; on fast courts the contact-position distribution is more "
            "compressed because rallies end earlier and extreme defensive positions are rarer."
        ),
        "magnitude": (
            "The winner-to-error ratio from inside-baseline contacts is typically 2.5-4x that "
            "of equivalent aggression from deep contacts, making court-position management one "
            "of the highest-leverage levers in the efficiency curve hierarchy."
        ),
        "links": [
            "rally_tolerance_consistency_curve",
            "depth_versus_safety_margin_tradeoff",
            "net_approach_risk_reward_curve",
            "return_aggression_risk_curve",
        ],
    },
    {
        "slug": "net_approach_risk_reward_curve",
        "title": "Net-Approach Risk-Reward Curve",
        "summary": (
            "Describes how net-approach frequency trades closing-efficiency gains against "
            "passing-shot exposure, with a depth threshold for approach balls below which "
            "the approach generates negative expected returns."
        ),
        "stat_signature": (
            "Net points won: 62-70% from approach balls landing within 1 metre of the baseline; "
            "45-55% from mid-court depth approaches; net-approach efficiency collapses to "
            "35-42% on approaches landing above the service line."
        ),
        "mechanism": (
            "A deep approach ball pushes the opponent wide and back, reducing passing-shot "
            "angle and time; a shallow approach allows comfortable passing angles and lob "
            "options. The depth threshold is the contact zone at which the distribution of "
            "opponent responses shifts from defensive to offensive."
        ),
        "conditions": (
            "Net-approach payoff is higher on fast surfaces where the closing-advantage is "
            "amplified by low bounce and fast approach balls; on clay the bounce allows "
            "opponents more time and higher contact, shifting the depth threshold deeper."
        ),
        "magnitude": (
            "Crossing from approach-depth quartile 1 to quartile 4 (shallow to deep) is "
            "associated with a 20-28 pp shift in net-points-won, among the widest efficiency "
            "gaps of any tactical binary in the stroke repertoire."
        ),
        "links": [
            "court_position_aggression_payoff",
            "drop_shot_risk_reward_curve",
            "depth_versus_safety_margin_tradeoff",
            "return_aggression_risk_curve",
        ],
    },
    {
        "slug": "depth_versus_safety_margin_tradeoff",
        "title": "Depth-Against-Safety-Margin Tradeoff",
        "summary": (
            "Captures the tradeoff between targeting greater baseline depth and maintaining "
            "net-clearance and sideline safety margin, tracing the forced-error gain against "
            "the unforced-error rise as margin shrinks."
        ),
        "stat_signature": (
            "Forced-error generation rises ~3 pp per additional 30 cm of average landing depth "
            "inside the baseline; unforced-error rate rises ~1.8 pp per 10 cm reduction in "
            "average net clearance below 40 cm when targeting baseline depth simultaneously."
        ),
        "mechanism": (
            "Deeper landing zones compress opponent response time and push contacts higher and "
            "further back, but achieving greater depth at pace requires trajectories with lower "
            "net clearance; the two constraints interact, and the optimal margin is the "
            "net-clearance value that maximises forced minus unforced errors per rally."
        ),
        "conditions": (
            "Tradeoff is most acute on clay where heavy topspin allows depth with more clearance; "
            "on hard courts depth-with-clearance requires faster racket speed that costs control. "
            "Wind and altitude shift the efficient margin bands significantly."
        ),
        "magnitude": (
            "Optimal-depth targeting versus conservative-depth patterns correlates with "
            "4-8 pp more forced errors per rally, partially offset by 2-3 pp more unforced "
            "errors — net-positive across the tour average baseline archetype."
        ),
        "links": [
            "court_position_aggression_payoff",
            "spin_pace_control_tradeoff",
            "aggression_error_tradeoff_curve",
        ],
    },
    {
        "slug": "spin_pace_control_tradeoff",
        "title": "Spin-Pace Control Tradeoff",
        "summary": (
            "Describes how trading flat pace for topspin or slice shifts the control-and-margin "
            "frontier, tracing the unforced-error reduction against the winner-rate cost "
            "across spin-rate bands at matched pace intent."
        ),
        "stat_signature": (
            "Heavy topspin (2000+ rpm) reduces unforced-error rate by 3-6 pp relative to "
            "flat pace equivalents; winner rate declines 4-8 pp at equivalent ball speed; "
            "hybrid mid-spin (1200-1800 rpm) sits closest to the frontier peak on hard courts."
        ),
        "mechanism": (
            "Topspin adds net clearance through a looping trajectory while pulling the ball "
            "down into the court, reducing both net-tape and wide-out errors; the cost is "
            "reduced ball speed at bounce that allows opponents more time and higher contact, "
            "lowering outright winner probability."
        ),
        "conditions": (
            "Topspin control benefit is largest at high altitude where the ball travels further "
            "and flat shots kick unpredictably; spin-rate benefit is reduced in wet cold "
            "conditions where balls sit heavy and respond less to rpm."
        ),
        "magnitude": (
            "Shift from low-spin to high-spin patterns at equivalent intent reduces outright "
            "winners by roughly 5 pp but cuts unforced errors 4 pp, a near-neutral net shift "
            "in total points won with a large composition change in how points are won."
        ),
        "links": [
            "depth_versus_safety_margin_tradeoff",
            "aggression_error_tradeoff_curve",
            "rally_tolerance_consistency_curve",
            "surface_aggression_payoff_shift",
        ],
    },
    {
        "slug": "serve_plus_one_aggression_curve",
        "title": "Serve-Plus-One Aggression Curve",
        "summary": (
            "Traces how aggressively attacking the third ball trades free serve-plus-one winners "
            "against early-error risk, measured as the points-won gain against the error-rate "
            "cost across attack-intent levels on the first groundstroke after serve."
        ),
        "stat_signature": (
            "Serve-plus-one points won: 68-76% with aggressive third-ball attack; 58-65% with "
            "neutral construction; serve-plus-one unforced-error rate rises from 4% at neutral "
            "intent to 9-13% at maximum aggression intent on the third ball."
        ),
        "mechanism": (
            "A well-placed serve creates a short or floating return that offers a geometric "
            "angle advantage on the third ball; the server's aggression intent can exploit "
            "this setup for a direct winner or structure winner, but over-swinging on a "
            "floating ball widens the distribution and sacrifices the position advantage."
        ),
        "conditions": (
            "Payoff is highest when serve placement creates a specific return zone (wide T "
            "serves pulling the opponent off court on the first-serve); diminished when "
            "return is neutralised or when the opponent possesses a flat, redirecting return."
        ),
        "magnitude": (
            "Optimal serve-plus-one aggression correlates with 8-12 pp more points won than "
            "passive construction on the third ball; over-aggression beyond the inflection "
            "costs 5-9 pp relative to the neutral benchmark."
        ),
        "links": [
            "first_serve_pace_in_rate_tradeoff",
            "court_position_aggression_payoff",
            "first_strike_versus_attrition_efficiency",
            "risk_reward_inflection_aggression",
        ],
    },
    {
        "slug": "first_strike_versus_attrition_efficiency",
        "title": "First-Strike-Against-Attrition Efficiency Curve",
        "summary": (
            "Describes how a player's point-win efficiency shifts along the first-strike-to-attrition "
            "continuum, tracing points won by rally-length regime and the strategy mix that "
            "maximises expected points across surface pace contexts."
        ),
        "stat_signature": (
            "First-strike archetypes win 68-74% of 1-3 stroke rallies but only 46-52% of 9+ "
            "stroke rallies; attrition archetypes win 50-55% of 1-3 stroke rallies and 55-62% "
            "of 9+ stroke rallies; mixed strategies sit between and are surface-dependent."
        ),
        "mechanism": (
            "First-strike efficiency draws on serve-and-winner sequencing that collapses points "
            "before the opponent's rally game activates; attrition efficiency draws on low "
            "unforced-error rates and forcing opponent aggression to self-implode at long-rally "
            "lengths. The two mechanisms are partially opposed at the portfolio level."
        ),
        "conditions": (
            "First-strike dominates on fast surfaces with low bounce; attrition dominates on "
            "slow clay where rally-tolerance errors are amplified and margins are sustainable. "
            "Optimal mix is surface-pace-specific and shifts further with opponent archetype."
        ),
        "magnitude": (
            "A pure first-striker operating on clay in extended rallies underperforms their "
            "expected points won by 6-10 pp in the 9+ stroke regime; an attrition specialist "
            "underperforms by a similar margin on grass in the 1-3 stroke regime."
        ),
        "links": [
            "rally_tolerance_consistency_curve",
            "surface_aggression_payoff_shift",
            "serve_plus_one_aggression_curve",
            "winner_to_error_efficient_frontier",
        ],
    },
    {
        "slug": "high_leverage_aggression_regression",
        "title": "High-Leverage Aggression Regression Curve",
        "summary": (
            "Captures how aggression intent and its associated error cost shift on high-pressure "
            "points, tracing the change in winner and error rates between leverage-weighted and "
            "baseline points and the resulting conversion slope."
        ),
        "stat_signature": (
            "Unforced-error rates rise 2-5 pp on break-point and set-point scenarios versus "
            "baseline; winner rates shift by smaller magnitudes (0.5-2 pp); the net leverage "
            "penalty in points-won averages 1.5-3 pp across tour-level samples."
        ),
        "mechanism": (
            "Elevated leverage activates physiological and cognitive arousal that narrows "
            "attentional focus and disrupts motor program execution at the margins of technique; "
            "this tightens the swing arc, reducing natural pace and altering trajectory — "
            "the net effect is a lower-quality error distribution without a compensating winner gain."
        ),
        "conditions": (
            "Effect is largest on prolonged leverage (multiple consecutive break-point conversions "
            "required) and when combined with fatigue in late sets; smallest under moderate "
            "leverage (advantage points) where arousal is contained."
        ),
        "magnitude": (
            "The 2-5 pp leverage-induced UE increase represents one of the more stable "
            "sport-wide efficiency curve shifts — observable across surfaces and archetypes — "
            "and accounts for a measurable fraction of break-point conversion rate variance."
        ),
        "links": [
            "margin_compression_under_pressure_curve",
            "winner_to_error_efficient_frontier",
            "fatigue_aggression_sustainability_curve",
            "risk_reward_inflection_aggression",
        ],
    },
    {
        "slug": "surface_aggression_payoff_shift",
        "title": "Surface Aggression-Payoff Shift",
        "summary": (
            "Describes how the aggression-error tradeoff curve translates across court surfaces, "
            "tracing the change in winner-to-error slope between fast and slow surfaces from "
            "differential bounce height, ball pace retention, and margin geometry."
        ),
        "stat_signature": (
            "Winner-to-error ratio at equivalent aggression is 1.3-1.7x higher on grass/fast "
            "hard versus clay; optimal aggression band shifts rightward (higher pace) by "
            "approximately 10-20 km/h from clay to fast hard to grass."
        ),
        "mechanism": (
            "Fast surfaces accelerate ball pace through low bounce, shortening opponent reaction "
            "time per unit of hitter aggression; slow surfaces add topspin lift and time, "
            "blunting the aggression payoff and pushing the winner-rate plateau lower. "
            "The efficient frontier is thus surface-specific."
        ),
        "conditions": (
            "Surface shift interacts with ball type (heavier balls reduce the fast-surface "
            "payoff amplification); indoor versus outdoor humidity shifts the effective surface "
            "pace band even on nominally identical courts."
        ),
        "magnitude": (
            "A 10th-percentile aggression increase yields roughly 2.5 pp more winners on "
            "fast hard versus 0.8 pp more on clay at equivalent contact quality — a 3x "
            "amplification of the aggression-payoff slope attributable to surface alone."
        ),
        "links": [
            "aggression_error_tradeoff_curve",
            "first_strike_versus_attrition_efficiency",
            "spin_pace_control_tradeoff",
            "shot_tolerance_against_pace_curve",
        ],
    },
    {
        "slug": "fatigue_aggression_sustainability_curve",
        "title": "Fatigue Aggression-Sustainability Curve",
        "summary": (
            "Traces how sustainable aggressive shotmaking is as match load accumulates, measuring "
            "unforced-error-rate rise and winner-rate decay per additional set under a fixed "
            "aggression intent."
        ),
        "stat_signature": (
            "Unforced-error rate rises on average 1.5-3 pp per set in matches extending beyond "
            "3 sets; winner rate declines 0.8-1.5 pp per set under maintained aggression; "
            "total aggression-sustainability decay averages 2-4 pp net-points-won per additional set."
        ),
        "mechanism": (
            "Peripheral muscle fatigue reduces racket-head speed ceiling and increases "
            "swing-path variability; central fatigue impairs real-time margin calibration. "
            "Together these widen the distribution of shot outcomes under fixed intent, "
            "increasing error frequency without reducing winner intent."
        ),
        "conditions": (
            "Decay accelerates in extreme heat or high humidity; decelerated in short best-of-3 "
            "formats or after extended rest between sets. Players with higher aerobic base show "
            "flatter fatigue curves through sets 4-5."
        ),
        "magnitude": (
            "In 5-set matches, the set-5 unforced-error rate is 3-6 pp above the set-1 baseline "
            "at similar aggression intent — a degradation comparable in points-won impact to "
            "playing the entire final set against a one-rank-stronger opponent."
        ),
        "links": [
            "high_leverage_aggression_regression",
            "risk_reward_inflection_aggression",
            "rally_tolerance_consistency_curve",
            "aggression_error_tradeoff_curve",
        ],
    },
    {
        "slug": "drop_shot_risk_reward_curve",
        "title": "Drop-Shot Risk-Reward Curve",
        "summary": (
            "Describes how drop-shot usage trades outright-winner and forced-error gains against "
            "drop-shot execution errors and counter-attack exposure, measured as points-won rate "
            "across usage frequency and court-position context."
        ),
        "stat_signature": (
            "Drop shots executed from inside the service line win outright 48-58% of points; "
            "from behind the baseline: 28-38%; execution error rate rises from ~6% at low "
            "frequency use to 11-15% at high frequency (opponent pattern recognition increases)."
        ),
        "mechanism": (
            "The drop shot creates a plane-change forcing opponent sprint forward from a "
            "deep rally position; its effectiveness depends on disguise and court position. "
            "Overuse reduces disguise quality, lifting opponent anticipation and counter-pass "
            "rate, bending the efficiency curve downward at high frequency."
        ),
        "conditions": (
            "Highest payoff on clay when opponent is pinned deep and tiring; lowest payoff "
            "on fast surfaces where the opponent closes quickly and the ball bounces higher. "
            "Opponent running speed is a primary external condition modifier."
        ),
        "magnitude": (
            "Transition from low (3-5% of rallies) to moderate (8-12%) drop-shot frequency "
            "from inside the baseline adds 3-5 pp points won; increasing further to 15%+ "
            "returns near-zero or negative marginal gain as opponent reads the pattern."
        ),
        "links": [
            "net_approach_risk_reward_curve",
            "court_position_aggression_payoff",
            "rally_tolerance_consistency_curve",
        ],
    },
    {
        "slug": "margin_compression_under_pressure_curve",
        "title": "Margin-Compression-Under-Pressure Curve",
        "summary": (
            "Captures how net-clearance and sideline-safety margins shrink as point importance "
            "rises, tracing the reduction in shot safety margin and the accompanying error-rate "
            "change across leverage tiers."
        ),
        "stat_signature": (
            "Average net clearance on groundstrokes declines 3-7 cm on break-point and set-point "
            "scenarios versus neutral points; sideline-target proximity rises by roughly 8-12 cm "
            "on average; unforced errors on high-leverage points exceed baseline by 2-5 pp."
        ),
        "mechanism": (
            "Pressure-induced technical changes — tightened grip, shortened backswing, altered "
            "contact point — produce flatter, faster stroke paths that reduce net clearance "
            "and pull shots toward lines. The margin compression is not purely attentional; "
            "biomechanical disruption is the primary driver."
        ),
        "conditions": (
            "Largest on serve-return under pressure where the shorter preparation window "
            "amplifies any biomechanical disruption; smaller on serve where the ritual "
            "preparation sequence partially buffers arousal effects."
        ),
        "magnitude": (
            "The 3-7 cm clearance reduction under pressure is sufficient to shift the "
            "net-fault probability from ~1% to 3-5% on flatter baseline drives, "
            "accounting for a disproportionate share of the leverage-point error rate increase."
        ),
        "links": [
            "high_leverage_aggression_regression",
            "risk_reward_inflection_aggression",
            "second_serve_aggression_double_fault_curve",
            "depth_versus_safety_margin_tradeoff",
        ],
    },
    {
        "slug": "second_serve_return_attack_efficiency",
        "title": "Second-Serve Return-Attack Efficiency Curve",
        "summary": (
            "The return-aggression tradeoff specific to the exploitable second serve, "
            "measuring return-points-won gain against return-error cost per aggression unit "
            "on second-serve deliveries across serve types and placement zones."
        ),
        "stat_signature": (
            "Return points won on second serve: 52-58% at tour average; rises to 60-66% "
            "with aggressive return intent but return-error rate increases from 6% to 10-15%; "
            "net optimal return aggression is approximately the 65th-75th aggression percentile."
        ),
        "mechanism": (
            "Second serves carry lower pace and more predictable trajectory, offering the returner "
            "additional contact preparation time; this shifts the aggression-payoff curve "
            "rightward compared with first-serve returns. However, kick serves with extreme "
            "spin create high-bounce contacts that widen the distribution and partially "
            "neutralise the pace-time advantage."
        ),
        "conditions": (
            "Attack payoff is largest against flat second serves in the middle of the box; "
            "reduced against heavy kick to the backhand where extreme bounce height forces "
            "a cramped contact zone. Slow surfaces extend the available contact window, "
            "flattening the return-error-rate curve at higher aggression levels."
        ),
        "magnitude": (
            "Optimal aggressive return intent on second serves adds 6-10 pp in return-points-won "
            "relative to passive construction; this is one of the largest marginal-leverage "
            "gains available from a single tactical adjustment in the return game."
        ),
        "links": [
            "second_serve_aggression_double_fault_curve",
            "return_aggression_risk_curve",
            "aggression_error_tradeoff_curve",
            "high_leverage_aggression_regression",
        ],
    },
    {
        "slug": "return_aggression_risk_curve",
        "title": "Return-Aggression Risk Curve",
        "summary": (
            "Traces the tradeoff between aggressive return intent and return-in rate across "
            "serve speeds and types, measuring return-points-won gain against return-error-rate "
            "cost per unit of return-swing aggression by serve classification."
        ),
        "stat_signature": (
            "Return-in rate on first serves: 73-82% at neutral intent, declining to 60-68% "
            "at maximum return aggression; on second serves, return-in rate stays 85-92% at "
            "neutral and 75-83% at aggressive intent — a wider actionable aggression window."
        ),
        "mechanism": (
            "Return aggression requires an earlier contact point and a more committed swing "
            "path, both of which reduce the contact-quality distribution and widen the "
            "error-zone for net or wide misses; faster incoming pace compresses preparation "
            "time, shifting the error-rate curve leftward and steepening the decline."
        ),
        "conditions": (
            "Aggression window on returns is wider on second serves, kick serves, and slow "
            "surfaces; narrowest on fast flat serves above 190 km/h where the reaction-time "
            "constraint dominates and any swing aggression above neutral adds large error cost."
        ),
        "magnitude": (
            "Aggressive return intent on second serves adds 5-9 pp in return-points-won at "
            "reasonable error cost; the same aggression level on fast first serves costs "
            "more in unforced return errors than it gains — a clear case of serve-type "
            "conditional optimal behavior."
        ),
        "links": [
            "second_serve_return_attack_efficiency",
            "court_position_aggression_payoff",
            "aggression_error_tradeoff_curve",
            "first_serve_pace_in_rate_tradeoff",
        ],
    },
]
