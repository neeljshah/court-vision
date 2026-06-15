"""scripts.platformkit.specs.disciplinecontrol_mlb — MLB DisciplineControl concept nodes.

Person-free, market-honest intelligence spec for the brain rebuild pipeline.
All fields are descriptive calibration intelligence; no edge or ROI is claimed.
"""
from __future__ import annotations

SPORT: str = "MLB"
FAMILY: str = "DisciplineControl"

CONCEPTS: list[dict] = [
    {
        "slug": "walk_rate_command_discipline",
        "title": "Walk-Rate Command Discipline",
        "summary": (
            "A pitcher's avoidance of free passes is anchored in in-zone command: "
            "pitchers below 2.5 BB/9 hold zone rate above 48% and unintentional-walk "
            "rate below 6%, while command-deficient arms (4+ BB/9) drift under 44% zone."
        ),
        "stat_signature": (
            "BB/9 (<2.5 elite, 3.5+ concern); unintentional-BB%; in-zone pitch% "
            "(48%+ correlates with sub-3 BB/9 at r ≈ 0.62 across starters)."
        ),
        "mechanism": (
            "In-zone rate drives count leverage: working ahead reduces the need to "
            "throw strikes under duress. When zone% falls, batters can take borderline "
            "pitches knowing the pitcher must come back, inflating walk probability per PA."
        ),
        "conditions": (
            "Amplified facing patient lineups (team BB% >9%), in hitter-friendly parks "
            "with tight zones, and after pitch counts exceed 75 as command fatigues. "
            "Cold-weather early season and high-humidity environments also degrade release."
        ),
        "magnitude": (
            "A 1-unit increase in BB/9 raises expected runs allowed per game by roughly "
            "0.35-0.45 runs through baserunner inflation, independent of hits allowed."
        ),
        "links": [
            "three_ball_count_avoidance",
            "first_pitch_strike_foundation",
            "command_collapse_inning_spiral",
            "two_strike_putaway_efficiency",
            "free_base_run_value_concession",
        ],
    },
    {
        "slug": "three_ball_count_avoidance",
        "title": "Three-Ball-Count Avoidance",
        "summary": (
            "Plate appearances reaching a 3-ball count convert to walks at 45-55% rates "
            "even for above-average command pitchers, making count avoidance a primary "
            "lever for suppressing on-base percentage beyond what hits-allowed captures."
        ),
        "stat_signature": (
            "3-ball count reach rate (% of PA); walk-conversion rate from 3-0, 3-1, "
            "3-2 counts; swinging-strike rate in 3-ball counts (elite >12% in those counts)."
        ),
        "mechanism": (
            "A 3-ball count structurally shifts leverage to the hitter: the pitcher must "
            "throw a hittable strike or gift a walk, collapsing the pitch-type and location "
            "decision tree. Even strong secondary offerings become less effective as hitters "
            "narrow zone coverage with a free pass in reach."
        ),
        "conditions": (
            "Most damaging with runners already on base (walk converts traffic to multi-threat), "
            "against patient high-walk lineups, and when the bullpen is taxed and the starter "
            "must avoid deep counts to conserve pitch budget."
        ),
        "magnitude": (
            "Pitchers with 3-ball count reach rates above 35% surrender on-base rates "
            "roughly 30-40 points higher than those below 28%, controlling for hit-type mix."
        ),
        "links": [
            "walk_rate_command_discipline",
            "first_pitch_strike_foundation",
            "command_collapse_inning_spiral",
            "two_strike_putaway_efficiency",
        ],
    },
    {
        "slug": "first_pitch_strike_foundation",
        "title": "First-Pitch-Strike Foundation",
        "summary": (
            "Getting ahead 0-1 is the single largest count-leverage fork: pitchers with "
            "first-pitch-strike rates above 63% post walk rates 1.2-1.8 BB/9 lower than "
            "those below 58%, and opponents hit roughly .040-.060 points lower on OBP."
        ),
        "stat_signature": (
            "First-pitch strike% (F-Strike%; elite 63%+, concern <58%); OBP split "
            "0-1 count versus 1-0 count start (gap typically .080-.110 points in OBP)."
        ),
        "mechanism": (
            "The 0-1 count doubles the pitcher's pitch-type flexibility, enabling off-speed "
            "and breaking balls in borderline locations the batter cannot take safely. "
            "The 1-0 count forces the pitcher toward the heart of the zone or risks walking "
            "the batter, compressing the effective command zone by roughly 15-20%."
        ),
        "conditions": (
            "Effect is strongest against disciplined contact hitters who rarely expand "
            "the zone. Less impactful against free-swinging lineups that chase heavily "
            "regardless of count. Magnified in late-game leverage when counts compound."
        ),
        "magnitude": (
            "A 5-point improvement in F-Strike% corresponds to roughly 0.25 BB/9 reduction "
            "and a measurable walk-driven ERA improvement of 0.15-0.25 on average."
        ),
        "links": [
            "walk_rate_command_discipline",
            "three_ball_count_avoidance",
            "two_strike_putaway_efficiency",
            "command_collapse_inning_spiral",
        ],
    },
    {
        "slug": "free_pass_baserunner_inflation",
        "title": "Free-Pass Baserunner Inflation",
        "summary": (
            "Walks and hit batters inflate baserunner traffic without requiring batted-ball "
            "contact, making them structurally more damaging than their event-rate suggests "
            "because they preserve out-count while loading the bases."
        ),
        "stat_signature": (
            "(BB + HBP) as % of total baserunners; free-base traffic per 9 innings "
            "(walk + HBP per 9); WHIP decomposition into hit-driven versus free-base-driven."
        ),
        "mechanism": (
            "Each unearned baserunner from a walk or HBP uses an out-count slot identically "
            "to a hit, but arrives with 100% base-reaching certainty and zero defensive "
            "assistance possible. In run-expectancy terms, a walk scores roughly 0.33 runs "
            "in expectation across game states, nearly matching a single."
        ),
        "conditions": (
            "Most harmful in innings where the pitcher already allowed a hit (second baserunner "
            "in an inning raises run expectancy far more than the first). Especially costly "
            "in narrow-lead situations where one run changes win probability sharply."
        ),
        "magnitude": (
            "Arms with free-base share above 30% of total baserunners allowed tend to "
            "yield 0.4-0.6 more runs per 9 than equivalent WHIP pitchers driven by hits, "
            "because free passes cluster in bad outings more than hits do."
        ),
        "links": [
            "walk_rate_command_discipline",
            "hit_by_pitch_control",
            "free_base_run_value_concession",
            "command_collapse_inning_spiral",
        ],
    },
    {
        "slug": "hit_by_pitch_control",
        "title": "Hit-By-Pitch and Inside-Miss Control",
        "summary": (
            "Plunking a hitter on a misfired inside pitch donates a free base identical "
            "in value to a walk while also risking a defensive disruption; HBP rates above "
            "0.45 per 9 innings signal persistent inside-command breakdown."
        ),
        "stat_signature": (
            "HBP/9 (0.45+ elevated; 0.3 or below is clean); inside-miss% on two-strike "
            "or two-out counts; glove-side release-point variance as a leading indicator."
        ),
        "mechanism": (
            "Inside fastballs and cut fastballs that tail further than intended cross the "
            "batter's hands rather than the inside corner. With two strikes pitchers attack "
            "inside more aggressively, raising the tail-inside exposure. Release-point scatter "
            "in the vertical plane is the most predictive precursor of HBP clusters."
        ),
        "conditions": (
            "Elevated in cold weather (glove stiffness reduces fingertip feel), when a "
            "pitcher is working through mechanics adjustments, and against deep-stance or "
            "plate-crowding batters who shrink the inside margin."
        ),
        "magnitude": (
            "Each 0.1-unit rise in HBP/9 adds roughly 0.12-0.15 runs per 9 to expected "
            "runs allowed through direct base-inflation; indirect effects from altered "
            "pitch-sequence risk tolerance add 0.05-0.10 more."
        ),
        "links": [
            "free_pass_baserunner_inflation",
            "walk_rate_command_discipline",
            "free_base_run_value_concession",
            "balk_set_position_discipline",
        ],
    },
    {
        "slug": "wild_pitch_avoidance",
        "title": "Wild-Pitch Avoidance",
        "summary": (
            "Uncatchable pitches that bounce in the dirt with runners on base directly "
            "advance those runners; pitchers exceeding 0.6 wild pitches per 9 innings "
            "donate roughly one extra advancement event per 15 innings of in-traffic work."
        ),
        "stat_signature": (
            "WP/9 (with-runners-on subsplit preferred); dirt-ball% on breaking balls "
            "(<7% clean, >11% elevated); blocked-ball rate versus uncatchable-ball rate split."
        ),
        "mechanism": (
            "Breaking balls with high vertical drop or sliders with heavy run that miss "
            "the catcher's frame and bounce unpredictably in the dirt cannot be controlled "
            "by blocking fundamentals alone. The pitcher's ability to bury the pitch within "
            "a catchable arc determines whether the receiver can prevent advancement."
        ),
        "conditions": (
            "Highest risk on 3-2 counts where the pitcher must commit to a sharp breaking "
            "ball for the strikeout, with runners who read the ball-in-dirt trigger well. "
            "Turf surfaces allow faster, more unpredictable bounces than dirt infields."
        ),
        "magnitude": (
            "Each wild pitch with a runner on second advances that runner to third and "
            "raises single-run scoring probability by roughly 20-25 percentage points in "
            "close-game states, a non-trivial run-expectancy jump per event."
        ),
        "links": [
            "passed_ball_block_discipline",
            "free_base_run_value_concession",
            "command_collapse_inning_spiral",
            "balk_set_position_discipline",
        ],
    },
    {
        "slug": "passed_ball_block_discipline",
        "title": "Passed-Ball and Blocking Discipline",
        "summary": (
            "A receiver's failure to corral a catchable dirt pitch surrenders free "
            "advancements attributable to defensive handling rather than pitch quality; "
            "blocks-above-average per 100 dirt pitches cleanly separates receiver tiers."
        ),
        "stat_signature": (
            "Passed balls per 162 games (>6 is elevated); blocks-above-average/100 dirt "
            "pitches (Statcast framing/blocking metric); passed-ball share of total "
            "wild-pitch-plus-passed-ball events (receiver accountability split)."
        ),
        "mechanism": (
            "Elite blockers use glove-positioning and drop-to-knees technique to cut off "
            "balls in the dirt before they pass, keeping runners from reading the ball-in-play "
            "trigger. Poor blocking receivers allow catchable pitches to skip to the backstop "
            "because technique breaks down on lateral or short-hop balls."
        ),
        "conditions": (
            "Most impactful with heavy sinker/sweeper pitching staffs that generate high "
            "dirt-contact rates by design, and in late-inning high-leverage situations "
            "with runners in scoring position where one advancement can change the outcome."
        ),
        "magnitude": (
            "The gap between elite-blocking and below-average receivers spans roughly "
            "8-12 advancements avoided per season, translating to 3-5 runs prevented "
            "through traffic management across a full year."
        ),
        "links": [
            "wild_pitch_avoidance",
            "catcher_throwing_giveaway",
            "free_base_run_value_concession",
        ],
    },
    {
        "slug": "fielding_error_rate",
        "title": "Fielding-Error Rate",
        "summary": (
            "Self-inflicted defensive misplays on routine and reachable balls extend "
            "innings without requiring pitcher failure; teams with fielding-error rates "
            "above 0.75 errors per game allow roughly 0.35-0.45 extra unearned runs per 9."
        ),
        "stat_signature": (
            "Errors per 162 games (team); fielding% by position (SS below .972 is "
            "elevated concern); routine-play conversion rate as an unscored-error supplement."
        ),
        "mechanism": (
            "Errors reset or extend out counts, forcing pitchers to record additional outs "
            "and increasing pitch counts and traffic simultaneously. Each error in an inning "
            "roughly doubles the probability that inning scores, because a baserunner is "
            "added without consuming an out."
        ),
        "conditions": (
            "Amplified on wet infields where true-hop reliability drops, in high-stadium-wind "
            "conditions affecting pop-up tracking, and under fatigue late in games when "
            "hand-eye coordination at corners and shortstop degrades."
        ),
        "magnitude": (
            "One additional team error per game above baseline corresponds to roughly "
            "0.3-0.4 additional unearned runs per 9, a non-trivial ERA-equivalent shift "
            "over a full season for a rotation that pitches 1,400+ innings."
        ),
        "links": [
            "throwing_error_propensity",
            "team_defensive_efficiency_misplay",
            "free_base_run_value_concession",
        ],
    },
    {
        "slug": "throwing_error_propensity",
        "title": "Throwing-Error Propensity",
        "summary": (
            "Errant throws that advance or reach base on error are disproportionately "
            "damaging because they often advance multiple runners; infield throwing errors "
            "account for roughly 55-60% of all errors but a higher share of multi-base gifts."
        ),
        "stat_signature": (
            "Throwing errors per throwing chance (E-throw/TC-throw); off-target rate on "
            "double-play pivots; arm-strength variance metric on pressure transfers."
        ),
        "mechanism": (
            "Throwing errors concentrate on double-play transfers and cut-off throws under "
            "time pressure, where the release must be condensed. Arm-angle deviations of "
            "5-8 degrees under stress produce throws that miss glove targets by 2-4 feet, "
            "enough to skip past receivers and enable multi-base advancements."
        ),
        "conditions": (
            "Highest frequency on 3-4-3 and 6-4-3 double-play attempts where pivot timing "
            "competes with the runner, and on outfield relay throws requiring accurate "
            "long-range arm targeting to cut-off men under physical exertion."
        ),
        "magnitude": (
            "A throwing error typically advances runners 1-2 additional bases beyond what "
            "a clean fielding play would have allowed; in scoring-position situations this "
            "raises run-scoring probability by 35-50 percentage points per event."
        ),
        "links": [
            "fielding_error_rate",
            "catcher_throwing_giveaway",
            "team_defensive_efficiency_misplay",
            "rundown_and_baserunning_blunder",
        ],
    },
    {
        "slug": "catcher_throwing_giveaway",
        "title": "Catcher Throwing and Caught-Stealing Giveaway",
        "summary": (
            "Errant throws on stolen-base attempts and pickoff attempts by the receiver "
            "convert a defensive play into a multi-base gift; throw-through-to-outfield "
            "rates above 4% of attempts signal genuine arm-accuracy breakdown."
        ),
        "stat_signature": (
            "Throwing errors per stolen-base attempt; wild-throw% on back-pickoff attempts; "
            "pop-time (below 1.90s elite) as the pre-condition for arm-accuracy pressure."
        ),
        "mechanism": (
            "Compressed release windows on stolen-base attempts push arm speed beyond "
            "repeatable mechanics; receivers with above-average pop-time but erratic "
            "accuracy trade one form of control for another. Pickoff attempts to second "
            "base require long cross-diamond throws at maximum effort, compounding error risk."
        ),
        "conditions": (
            "Most damaging with a runner on second and less than two outs, where an errant "
            "pickoff throw scores directly from second. Amplified against aggressive "
            "baserunning teams that force high-volume stolen-base attempt environments."
        ),
        "magnitude": (
            "A single errant throw to the outfield with runners in scoring position raises "
            "immediate run-scoring probability by 60-80 percentage points, making it among "
            "the highest per-event run-value misplays in the defensive repertoire."
        ),
        "links": [
            "throwing_error_propensity",
            "passed_ball_block_discipline",
            "pickoff_and_lead_management",
            "free_base_run_value_concession",
        ],
    },
    {
        "slug": "balk_set_position_discipline",
        "title": "Balk and Set-Position Discipline",
        "summary": (
            "Illegal-motion and deceptive-delivery balks gift a free advancement without "
            "a pitch, typically arising from abbreviated set positions or interrupted "
            "deliveries; pitchers with 3+ balks in a season show measurable set-position "
            "inconsistency under holding pressure."
        ),
        "stat_signature": (
            "Balks per 9 innings with runners on; balk rate per holding opportunity; "
            "share of balks traced to set-position vs. delivery interruption (film metric)."
        ),
        "mechanism": (
            "The set position requires a complete stop; pitchers who shorten the pause "
            "under urgency or use deceptive head-motion violate the rule. Runners who time "
            "the delivery and take extreme leads exert psychological pressure that increases "
            "abbreviated-stop probability among less-experienced or mechanics-fatigued pitchers."
        ),
        "conditions": (
            "Elevated with a fast runner on first who repeatedly draws step-off engagements, "
            "forcing the pitcher into a high-frequency hold rhythm that erodes set-position "
            "discipline. Also more common in late-season when mechanics fatigue accumulates."
        ),
        "magnitude": (
            "Each balk advances all runners one base; in a runner-on-second/no-out state "
            "the balk gifts roughly 0.40-0.55 expected runs by advancing the lead runner "
            "to third, a significant single-event cost from a procedural violation."
        ),
        "links": [
            "pitch_clock_violation_discipline",
            "wild_pitch_avoidance",
            "pickoff_and_lead_management",
            "free_base_run_value_concession",
        ],
    },
    {
        "slug": "pitch_clock_violation_discipline",
        "title": "Pitch-Clock Violation Discipline",
        "summary": (
            "Automatic balls from timer violations and disengagement-limit penalties impose "
            "a count-leverage tax directly analogous to a walk but entirely procedural; "
            "pitchers with 3+ violations per 100 IP show systematic readiness-sequencing "
            "breakdown rather than isolated incidents."
        ),
        "stat_signature": (
            "Timer violations per 9 innings; auto-ball rate per plate appearance; "
            "disengagement-penalty frequency when holding runners (limit-3 rule)."
        ),
        "mechanism": (
            "The 15-second and 20-second timer forces pitchers into fixed rhythm regardless "
            "of grip-reset, mound-visit timing, or catcher sign complexity. Violations "
            "inject automatic balls into count sequences, immediately shifting leverage to "
            "the hitter and compressing the pitcher's zone-attack flexibility."
        ),
        "conditions": (
            "Most damaging in 0-0 or 1-0 counts where an automatic ball produces a 2-0 or "
            "2-1 count, significantly raising walk probability. Pitchers with large sign "
            "sequences or slow grip-reset tendencies are structurally more vulnerable."
        ),
        "magnitude": (
            "An automatic ball in a 0-0 count is equivalent in count-leverage terms to "
            "throwing a first-pitch ball; the subsequent count-walk-conversion penalty "
            "mirrors a 0.08-0.12 increase in per-PA walk rate for that appearance."
        ),
        "links": [
            "balk_set_position_discipline",
            "walk_rate_command_discipline",
            "three_ball_count_avoidance",
            "free_base_run_value_concession",
        ],
    },
    {
        "slug": "two_strike_putaway_efficiency",
        "title": "Two-Strike Putaway and Free-Pass Leak",
        "summary": (
            "Reaching two strikes without converting to a strikeout and leaking into a walk "
            "is a dual-cost failure: the PA consumes extra pitches while donating a free "
            "base; elite putaway arms convert two-strike counts to outs at 75-80% rates "
            "while struggling arms convert below 65%."
        ),
        "stat_signature": (
            "K% from two-strike counts; walk% from two-strike counts (<3% elite, >7% "
            "concern); chase rate on two-strike offerings outside the zone."
        ),
        "mechanism": (
            "Two-strike nibbling — throwing borderline or out-of-zone pitches hoping for "
            "a chase — extends the PA without generating outs. Hitters who recognize "
            "two-strike chasing patterns take pitches and force the pitcher back into the "
            "zone, converting a dominant count into a walk rather than a strikeout."
        ),
        "conditions": (
            "Amplified facing disciplined lineups with two-strike walk rates above 5%. "
            "Especially costly in high-leverage situations where the pitcher prioritizes "
            "avoiding hard contact over aggressively attacking the zone."
        ),
        "magnitude": (
            "A two-strike walk is among the most expensive individual pitch-sequence "
            "outcomes: the pitcher had a dominant count advantage and converted it into "
            "a free base, a swing in expected outcome of roughly 0.5-0.65 runs per event."
        ),
        "links": [
            "walk_rate_command_discipline",
            "hitter_chase_discipline",
            "first_pitch_strike_foundation",
            "command_collapse_inning_spiral",
        ],
    },
    {
        "slug": "hitter_chase_discipline",
        "title": "Hitter Chase-Out-of-Zone Discipline",
        "summary": (
            "Batters who expand the zone on pitches outside the strike zone surrender "
            "contact quality and on-base probability simultaneously; out-of-zone swing "
            "rates above 32% correlate strongly with below-average walk rates and elevated "
            "weak-contact frequency on chased pitches."
        ),
        "stat_signature": (
            "O-Swing% (out-of-zone swing%; <25% disciplined, >32% chase-prone); "
            "contact quality on chased pitches (xwOBA on O-contact typically 40-60 points "
            "below in-zone contact); walk rate split for O-Swing% tiers."
        ),
        "mechanism": (
            "Chasing out-of-zone pitches converts pitcher mistakes (missed spots) into "
            "hitter mistakes (non-competitive swings), eliminating the walk opportunity "
            "while generating weak contact on pitches designed to be unhittable at that "
            "location. Each chase on a two-strike pitch ends an at-bat that a disciplined "
            "hitter might have extended to a walk or favorable count."
        ),
        "conditions": (
            "Maximally exploitable by pitchers with high-spin breaking balls that start "
            "in the zone and break out, and by high-velocity arms whose fastballs tunnel "
            "with out-of-zone secondary offerings. Chase rates rise predictably in two-strike "
            "counts and with runners on base when pressure to make contact increases."
        ),
        "magnitude": (
            "The OBP gap between a 22% O-Swing hitter and a 34% O-Swing hitter is roughly "
            ".040-.060 points, almost entirely driven by walk-rate differences, with "
            "secondary xwOBA losses on low-quality contact adding .020-.030 more."
        ),
        "links": [
            "two_strike_putaway_efficiency",
            "walk_rate_command_discipline",
            "double_play_avoidance_control",
        ],
    },
    {
        "slug": "command_collapse_inning_spiral",
        "title": "Command-Collapse Inning Spiral",
        "summary": (
            "Within an inning, a first walk sharply elevates the probability of a second "
            "walk or HBP as command erodes under traffic pressure; pitchers with 'inning-spiral' "
            "walk clustering — where 40%+ of walk innings contain 2+ free passes — are "
            "disproportionately expensive relative to their season-average BB/9."
        ),
        "stat_signature": (
            "Multi-walk inning rate (% of walk-innings with 2+ walks); consecutive-walk "
            "frequency (back-to-back walk probability given first walk of inning >15% "
            "signals spiral pattern); walk clustering index across starts."
        ),
        "mechanism": (
            "A first walk in an inning raises pitch-count pressure, narrows margin for error "
            "with first base occupied, and may trigger an umpire-zone-expansion perception "
            "effect. The resulting mechanical overcorrection — gripping too hard, rushing the "
            "tempo — compounds command deviation, making a second walk more likely than the "
            "first despite unchanged pitch mix."
        ),
        "conditions": (
            "Most pronounced for pitchers with high walk rates to begin with, in high-leverage "
            "late-game situations, and against lineups with deep, patient batting orders where "
            "the first-walk hitter typically is followed by equally disciplined bats."
        ),
        "magnitude": (
            "In innings with a first walk, the probability of allowing 3+ runs roughly doubles "
            "compared to innings begun cleanly; spiral-prone pitchers add 0.40-0.60 ERA-equivalent "
            "damage above what their raw BB/9 predicts due to clustering."
        ),
        "links": [
            "walk_rate_command_discipline",
            "three_ball_count_avoidance",
            "first_pitch_strike_foundation",
            "free_base_run_value_concession",
        ],
    },
    {
        "slug": "team_defensive_efficiency_misplay",
        "title": "Team Defensive-Efficiency and Misplay Profile",
        "summary": (
            "Defensive efficiency (balls in play converted to outs) and misplay rate capture "
            "defensive value that scored-error statistics systematically omit; teams with "
            "defensive efficiency below .685 on balls in play concede roughly 20-30 additional "
            "hits-in-play relative to the league midpoint per 162 games."
        ),
        "stat_signature": (
            "Defensive efficiency (outs on BIP / total BIP; league mid ~.690-.700); "
            "misplay rate per 100 BIP (scoring-convention-excluded misplays via Statcast); "
            "DRS and OAA as cross-validation benchmarks."
        ),
        "mechanism": (
            "Balls in play that a rangy, well-positioned defense converts to outs become "
            "singles or extra-base hits behind a below-average unit, inflating BABIP and "
            "creating discrepancy between pitcher ERA and FIP. The pitcher's run-prevention "
            "is partially a function of the defensive unit's structural conversion quality."
        ),
        "conditions": (
            "Most variable in spacious outfields where range separates elite and average units, "
            "and on infield shifts where positioning and footwork interact. Stadium dimensions "
            "amplify or compress the impact: cavernous outfields reward range more than "
            "bandbox parks where fewer balls reach the gaps."
        ),
        "magnitude": (
            "A 10-point defensive efficiency gap (e.g., .680 versus .690) corresponds to "
            "roughly 14-20 additional hits allowed per 162 games, translating to approximately "
            "7-12 extra runs allowed through BABIP inflation above the pitcher's true talent."
        ),
        "links": [
            "fielding_error_rate",
            "throwing_error_propensity",
            "free_base_run_value_concession",
        ],
    },
    {
        "slug": "free_base_run_value_concession",
        "title": "Free-Base Run-Value Concession",
        "summary": (
            "Walks, hit batters, wild pitches, balks, and errors combined donate run "
            "expectancy to the opposing offense without requiring a batted ball; "
            "quantifying these as aggregate expected runs per 9 separates clean-process "
            "run prevention from hit-luck-sensitive ERA."
        ),
        "stat_signature": (
            "Expected runs added per 9 from non-batted events (BB + HBP + WP + balk + "
            "errors combined, weighted by run-expectancy context); FIP-adjacent metric "
            "isolating self-inflicted free-base run value from hit-driven runs."
        ),
        "mechanism": (
            "Each non-batted free base occupies a base while preserving the out count, "
            "and their run expectancy is fully predictable from game-state tables. "
            "Aggregating across event types reveals whether a pitcher or defense is "
            "process-clean (low combined rate) or consistently self-inflicting damage "
            "independent of what happens when the ball is put in play."
        ),
        "conditions": (
            "Most informative over 80+ innings to stabilize rate estimates; most impactful "
            "in low-scoring environments where one free base per inning can represent "
            "the margin of a run scored. Also meaningful in evaluating bullpen arms where "
            "multi-inning free-base clustering is common."
        ),
        "magnitude": (
            "The spread between the cleanest and most self-inflicting pitching units on "
            "this combined metric is roughly 0.60-0.90 runs per 9 innings, a magnitude "
            "comparable to the difference between an average and above-average ERA tier, "
            "arising entirely from avoidable discipline and control lapses."
        ),
        "links": [
            "walk_rate_command_discipline",
            "hit_by_pitch_control",
            "wild_pitch_avoidance",
            "balk_set_position_discipline",
            "fielding_error_rate",
        ],
    },
]
