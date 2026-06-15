"""NBA DisciplineControl spec — foul and turnover discipline concepts.

Person-free, descriptive intelligence; no edge/ROI/pick claims.
"""
from __future__ import annotations

SPORT = "NBA"
FAMILY = "DisciplineControl"

CONCEPTS: list[dict] = [
    {
        "slug": "shooting_foul_propensity",
        "title": "Shooting-Foul Propensity on Contest",
        "summary": (
            "Measures how frequently a defender converts a rim or jump-shot contest "
            "into a shooting foul rather than a clean challenge, with the and-one "
            "share disaggregated from standard two-shot fouls."
        ),
        "stat_signature": (
            "Shooting fouls per 100 rim contests (baseline ~3-5); and-one share "
            "of shooting fouls (league ~18%); foul rate on jump-shot closeouts "
            "elevated above 1.5 per 100 indicates a pattern."
        ),
        "mechanism": (
            "Defenders who leave their feet early or swipe downward shift contact "
            "probability onto the shooter's wrist and arm; referee framing of the "
            "contest vertical plane penalizes any lateral displacement."
        ),
        "conditions": (
            "Elevated in high-pace transition contests and against aggressive "
            "shot-fakers; worsens when the defender closes out off-balance or "
            "from a running start rather than a set-feet approach."
        ),
        "magnitude": (
            "Each additional shooting foul per 100 possessions yields roughly "
            "0.5-0.8 extra opponent free-throw attempts per game; converting "
            "a clean block into a shooting foul shifts expected value by ~1.2 pts."
        ),
        "links": [
            "verticality_discipline_at_rim",
            "closeout_foul_control",
            "foul_trouble_aggression_tax",
            "offensive_to_defensive_foul_balance",
        ],
    },
    {
        "slug": "reach_in_perimeter_foul_rate",
        "title": "Reach-In and Perimeter Hand-Foul Rate",
        "summary": (
            "Captures avoidable on-ball fouls from reaching, hand-checking, and "
            "arm-bars against drives, normalized per 100 on-ball defensive matchups "
            "and per 100 opponent drives defended."
        ),
        "stat_signature": (
            "Perimeter fouls per 100 on-ball matchups (elevated above 4.5 flags risk); "
            "reach-in share of total personal fouls above 30% indicates poor discipline; "
            "delta rises sharply against quick first-step drivers."
        ),
        "mechanism": (
            "Reaching extends the defender's arm into the ball carrier's path, "
            "triggering referee contact rules on the forearm/hand; foot speed "
            "deficits are compensated by the arm, which the rulebook penalizes "
            "to protect ball-handler rhythm."
        ),
        "conditions": (
            "Most pronounced against speed-over-power guards who set up the reach "
            "with a hesitation; also elevated when the defender is in drop coverage "
            "and scrambles laterally to recover."
        ),
        "magnitude": (
            "Lineups with above-median reach-in rates concede 2-3 additional free "
            "throws per game; bonus situations reached ~4 possessions earlier per "
            "48 minutes compound the downstream free-throw burden."
        ),
        "links": [
            "shooting_foul_propensity",
            "early_foul_accumulation_pace",
            "off_ball_foul_leakage",
            "foul_trouble_aggression_tax",
        ],
    },
    {
        "slug": "off_ball_foul_leakage",
        "title": "Off-Ball Foul Leakage",
        "summary": (
            "Captures fouls committed away from the ball on screens, box-outs, and "
            "loose-ball scrambles, measured as off-ball fouls as a share of total fouls "
            "and per 100 defensive possessions."
        ),
        "stat_signature": (
            "Off-ball fouls above 35% of total personal fouls are a structural "
            "inefficiency; per 100 defensive possessions threshold >1.2 triggers "
            "elevated bonus risk; loose-ball foul share spikes in overtime contexts."
        ),
        "mechanism": (
            "Screen-navigation physicality and box-out wrestling create contact that "
            "referees call when the defensive player initiates; these fouls carry "
            "zero deterrence value and purely add to the bonus clock."
        ),
        "conditions": (
            "More frequent against heavy pick-and-roll schemes and against offensive "
            "rebounders who hunt contact; exacerbated in physical interior matchups "
            "where help defenders over-fight screens."
        ),
        "magnitude": (
            "Teams above the 75th percentile in off-ball foul rate enter the bonus "
            "roughly 3 possessions earlier per half, gifting ~1-2 extra opponent "
            "free-throw attempts per game on non-shot situations."
        ),
        "links": [
            "reach_in_perimeter_foul_rate",
            "early_foul_accumulation_pace",
            "foul_trouble_aggression_tax",
            "block_charge_decision_discipline",
        ],
    },
    {
        "slug": "early_foul_accumulation_pace",
        "title": "Early-Foul Accumulation Pace",
        "summary": (
            "Captures the rate at which a defender banks fouls in the first half "
            "independent of minutes, measuring fouls per defensive minute in the "
            "first 18 minutes and the probability of two-plus first-quarter fouls."
        ),
        "stat_signature": (
            "Fouls per 18 minutes above 2.0 in Q1-Q2 flags chronic early trouble; "
            "two-plus first-quarter foul probability above 15% is a meaningful threshold; "
            "single-season early-foul rate stable to +/-0.3 across comparable schedules."
        ),
        "mechanism": (
            "Early-game aggression and rim-protection instincts collide with the "
            "rulebook before the defender calibrates to that night's officiating crew; "
            "coaching response is minutes restriction that removes the player from "
            "critical stretch-run possessions."
        ),
        "conditions": (
            "Amplified against quick drive-and-draw guards who probe rim protectors "
            "in the first possession; crew tendencies and away-game officiating "
            "variance compound early foul accumulation."
        ),
        "magnitude": (
            "A starter sitting with two first-quarter fouls loses a median 6-8 "
            "minutes of second-quarter availability; defensive rating in those "
            "stretches rises by 4-7 points per 100 possessions without the anchor."
        ),
        "links": [
            "foul_trouble_aggression_tax",
            "shooting_foul_propensity",
            "verticality_discipline_at_rim",
            "off_ball_foul_leakage",
        ],
    },
    {
        "slug": "verticality_discipline_at_rim",
        "title": "Rim-Contest Verticality Discipline",
        "summary": (
            "Captures a rim protector's ability to challenge with set feet and a "
            "vertical plane rather than a swipe or body-displacement, measured via "
            "block-to-shooting-foul ratio on restricted-area contests."
        ),
        "stat_signature": (
            "Block-to-shooting-foul ratio above 3.0 on rim contests signals good "
            "verticality; bodily-displacement foul share above 20% of rim fouls "
            "indicates poor technique; elite protectors sustain ratios above 4.5."
        ),
        "mechanism": (
            "The rulebook protects the vertical plane once a defender's feet are "
            "set; any lateral lean or downward swipe creates arm/body contact that "
            "negates the block and shifts two free throws to the offense."
        ),
        "conditions": (
            "Most tested on two-foot gather finishes and eurostep attacks where the "
            "shooter can alter trajectory mid-air; less testable on straight-line "
            "one-foot approaches where timing dominates."
        ),
        "magnitude": (
            "Converting a shooting-foul contest into a clean block saves ~1.3 expected "
            "points; rim protectors in the top quartile of this ratio allow 0.08-0.12 "
            "fewer points per restricted-area possession than bottom-quartile peers."
        ),
        "links": [
            "shooting_foul_propensity",
            "block_charge_decision_discipline",
            "early_foul_accumulation_pace",
            "closeout_foul_control",
        ],
    },
    {
        "slug": "closeout_foul_control",
        "title": "Closeout Foul Control",
        "summary": (
            "Captures fouls conceded when a defender flies at a perimeter shooter, "
            "measured as shooting fouls on three-point attempts per 100 closeouts and "
            "the rate of running into the shooter's landing zone."
        ),
        "stat_signature": (
            "Three-point shooting fouls per 100 closeouts above 1.8 flags risk; "
            "landing-space violation share above 12% of closeout fouls is elevated; "
            "rate spikes for corner-three closeouts where runway is shorter."
        ),
        "mechanism": (
            "A closeout at full speed shifts momentum into the shooter's gather space; "
            "the referee awards three free throws when contact occurs on the release, "
            "making the sequence worth ~2.2 expected points — worse than a made three."
        ),
        "conditions": (
            "Worsened by heavy ball-movement offenses that generate open looks with "
            "defenders already in motion; also elevated in bonus situations where the "
            "offense deliberately seeks such contact."
        ),
        "magnitude": (
            "Each three-point shooting foul costs ~2.1 expected points above the "
            "defensive alternative; lineups in the top-quartile closeout-foul rate "
            "concede an estimated 3-4 extra points per game from this source alone."
        ),
        "links": [
            "shooting_foul_propensity",
            "verticality_discipline_at_rim",
            "reach_in_perimeter_foul_rate",
            "offensive_to_defensive_foul_balance",
        ],
    },
    {
        "slug": "block_charge_decision_discipline",
        "title": "Block-or-Charge Decision Discipline",
        "summary": (
            "Captures the help defender's choice between drawing a charge and "
            "conceding a blocking foul, measured as charges drawn versus blocking "
            "fouls per 100 help rotations and heel-on-arc error frequency."
        ),
        "stat_signature": (
            "Charge-to-blocking-foul ratio above 1.5 in help situations signals "
            "sound positioning; heel-off-arc error on drawn charges leads to "
            "referee reversal in roughly 25% of contested calls at the pro level."
        ),
        "mechanism": (
            "A legal charge requires two feet set inside the restricted area arc "
            "before the offensive player leaves the floor; late arrival converts "
            "the deterrence play into a blocking foul — identical contact, opposite outcome."
        ),
        "conditions": (
            "Most consequential on drive-and-kick recovery rotations and on pull-up "
            "mid-range attacks where arc positioning is ambiguous; fast-rotation "
            "help from the weak side makes early arc arrival structurally harder."
        ),
        "magnitude": (
            "A successful charge is a turnover plus a defensive foul removed; a "
            "blocking foul in a bonus situation costs ~1.7 expected points. "
            "Teams that lead the league in charges drawn gain roughly 2-3 extra "
            "defensive stops per game from this mechanic."
        ),
        "links": [
            "verticality_discipline_at_rim",
            "off_ball_foul_leakage",
            "offensive_foul_charge_exposure",
            "foul_trouble_aggression_tax",
        ],
    },
    {
        "slug": "live_ball_turnover_share",
        "title": "Live-Ball Turnover Share",
        "summary": (
            "Captures the fraction of giveaways that occur on a live ball and thus "
            "seed transition the other way, measured as live-ball turnovers as a share "
            "of total and transition points conceded per live-ball turnover."
        ),
        "stat_signature": (
            "League-average live-ball share ~55% of total turnovers; transition "
            "points per live-ball turnover ~1.1 versus ~0.5 for dead-ball; "
            "above-average transition offenses extract 1.3-1.5 from live-ball gifts."
        ),
        "mechanism": (
            "Stolen passes and deflected dribbles leave the defense out of rotation "
            "and the offense with numerical advantages; the two-on-one or three-on-two "
            "conversion rate dwarfs a typical half-court possession value."
        ),
        "conditions": (
            "Matters most against full-court pressure schemes and high-pace units; "
            "live-ball share rises when hub handlers are fatigued or defending "
            "extended possessions with active deflectors in the passing lane."
        ),
        "magnitude": (
            "Moving 5 percentage points of turnovers from dead-ball to live-ball "
            "category corresponds to roughly 1.5-2.0 additional opponent transition "
            "points per game based on typical conversion differentials."
        ),
        "links": [
            "bad_pass_turnover_propensity",
            "ball_handling_turnover_rate",
            "turnover_recovery_response",
            "team_turnover_economy_profile",
        ],
    },
    {
        "slug": "bad_pass_turnover_propensity",
        "title": "Bad-Pass Turnover Propensity",
        "summary": (
            "Captures errant passing into traffic, telegraphed skips, and entry-pass "
            "picks, measured as bad-pass turnovers per 100 passes thrown and per "
            "assist opportunity created."
        ),
        "stat_signature": (
            "Bad-pass turnovers per 100 passes above 1.8 is a structural liability; "
            "per assist opportunity above 0.25 flags risk in hub roles; "
            "entry-pass turnover rate against switching defenses rises 0.3-0.5."
        ),
        "mechanism": (
            "Telegraphed eye contact and predictable timing allow active defenders "
            "to jump passing lanes; skip passes over zone gaps are high-risk at any "
            "pressure level because the receiver's window is narrow."
        ),
        "conditions": (
            "Elevated against active-hands zone schemes and against switching defenses "
            "where passing angles collapse; fatigue in the fourth quarter inflates "
            "pass velocity errors on post entries."
        ),
        "magnitude": (
            "Each bad-pass turnover carries roughly 1.1 expected points cost to the "
            "offense; handlers in the 90th percentile of this rate produce "
            "approximately 2-3 more costly giveaways per 36 minutes than median."
        ),
        "links": [
            "live_ball_turnover_share",
            "pressure_induced_turnover_susceptibility",
            "double_team_turnover_resistance",
            "late_clock_turnover_risk",
        ],
    },
    {
        "slug": "ball_handling_turnover_rate",
        "title": "Ball-Handling and Lost-Dribble Rate",
        "summary": (
            "Captures dribble-related giveaways from strips, deflections, and travels "
            "under pressure, measured as ball-handling turnovers per 100 touches and "
            "per 100 isolation or drive possessions."
        ),
        "stat_signature": (
            "Ball-handling turnovers per 100 touches above 2.5 is elevated; "
            "strip rate per 100 isolation possessions above 4.0 signals vulnerability; "
            "travel calls per 100 gather sequences above 1.2 flags footwork instability."
        ),
        "mechanism": (
            "Active-hands defenders target the dribbling hand's transfer moment "
            "and the apex of the crossover; high-bodied dribbles and predictable "
            "change-of-direction timing increase exposure to clean strips."
        ),
        "conditions": (
            "Peaks against blitz-and-double schemes and against active-hands "
            "perimeter defenders; worsens at end of shot-clock when handler must "
            "improvise and control is sacrificed for reach."
        ),
        "magnitude": (
            "Handlers in the bottom quartile of ball-handling turnover rate generate "
            "roughly 1.8-2.5 extra giveaways per game versus top-quartile peers; "
            "strip-induced live-ball turnovers compound to ~2 transition points each."
        ),
        "links": [
            "live_ball_turnover_share",
            "late_clock_turnover_risk",
            "pressure_induced_turnover_susceptibility",
            "offensive_foul_charge_exposure",
        ],
    },
    {
        "slug": "offensive_foul_charge_exposure",
        "title": "Offensive-Foul and Charge Exposure",
        "summary": (
            "Captures self-inflicted offensive fouls from charges, illegal screens, "
            "and push-offs, measured as offensive fouls per 100 drives plus screens "
            "and the share charged on out-of-control attacks."
        ),
        "stat_signature": (
            "Offensive fouls per 100 drives above 2.0 flags recurring exposure; "
            "illegal-screen rate per 100 actions above 1.5 indicates contact-seeking "
            "screen technique; charge share above 40% of offensive fouls is high."
        ),
        "mechanism": (
            "Out-of-control drives into a legally set defender, and screen-setters "
            "who extend an arm or move into the cutter's path, trigger offensive fouls "
            "that nullify the possession and hand possession back without a reset."
        ),
        "conditions": (
            "More frequent against disciplined help-side defenses that plant early "
            "to draw charges; illegal screens rise against switching defenses that "
            "require contact-heavy navigation through the ball-screen action."
        ),
        "magnitude": (
            "Each offensive foul costs the full possession value (~1.05 pts) and "
            "removes one from the foul budget; lineups in the top quintile of "
            "offensive foul rate concede roughly 2 extra possessions per game."
        ),
        "links": [
            "block_charge_decision_discipline",
            "ball_handling_turnover_rate",
            "late_clock_turnover_risk",
            "team_turnover_economy_profile",
        ],
    },
    {
        "slug": "late_clock_turnover_risk",
        "title": "Late-Shot-Clock Turnover Risk",
        "summary": (
            "Captures elevated giveaway probability as the shot clock expires and "
            "decisions are rushed, measured as turnover rate in the final six seconds "
            "of the clock relative to the early-clock baseline."
        ),
        "stat_signature": (
            "Turnover rate in the final six seconds typically 2.5-3.5x early-clock "
            "baseline; teams that rely on one-on-one creation see the multiplier "
            "reach 4x when schemes break down in crunch clock."
        ),
        "mechanism": (
            "Shot-clock pressure forces handlers into contested pull-up opportunities "
            "or ill-timed passes; shot quality collapses and defensive contests "
            "improve simultaneously, raising the combined giveaway probability."
        ),
        "conditions": (
            "Amplified in half-court sets that exhaust the clock on primary actions; "
            "worsens against defenses that deliberately extend half-court possessions "
            "to manufacture late-clock entropy."
        ),
        "magnitude": (
            "Late-clock turnovers occur at roughly 2-3x the frequency of mid-clock, "
            "and because they are mostly live-ball, each one seeds ~1.1 opponent "
            "transition points; eliminating one per game is worth ~1.1 pts."
        ),
        "links": [
            "bad_pass_turnover_propensity",
            "ball_handling_turnover_rate",
            "pressure_induced_turnover_susceptibility",
            "live_ball_turnover_share",
        ],
    },
    {
        "slug": "pressure_induced_turnover_susceptibility",
        "title": "Pressure-Induced Turnover Susceptibility",
        "summary": (
            "Captures how much full-court and half-court ball pressure inflates a "
            "handler's giveaways, measured as the turnover-rate delta when defended "
            "by high-deflection pressure versus passive coverage."
        ),
        "stat_signature": (
            "Turnover rate delta of more than 3 percentage points under pressure "
            "versus passive coverage signals meaningful susceptibility; deflection "
            "rate of defending unit above 3.5 per game distinguishes high-pressure tiers."
        ),
        "mechanism": (
            "Active-hands trapping and denial schemes force earlier decisions on "
            "handlers who rely on time to read secondaries; compressed decision "
            "windows inflate bad-pass and bad-dribble errors simultaneously."
        ),
        "conditions": (
            "Most predictive for handlers with below-average handle tightness; "
            "manifests clearly in fourth quarters against defensive schemes that "
            "escalate pressure when protecting narrow leads."
        ),
        "magnitude": (
            "Susceptible handlers (top quartile of pressure delta) generate "
            "approximately 1.5-2.0 extra turnovers per 36 minutes against high-pressure "
            "defenses, each costing roughly 1.05 expected offensive points."
        ),
        "links": [
            "bad_pass_turnover_propensity",
            "double_team_turnover_resistance",
            "late_clock_turnover_risk",
            "ball_handling_turnover_rate",
        ],
    },
    {
        "slug": "double_team_turnover_resistance",
        "title": "Double-Team Turnover Resistance",
        "summary": (
            "Captures a hub's ability to pass out of traps cleanly rather than cough "
            "the ball up, measured as turnovers per 100 double-teams faced in the post "
            "or on the ball-screen."
        ),
        "stat_signature": (
            "Turnovers per 100 trap possessions above 18 indicates poor resistance; "
            "pass accuracy out of double-teams above 85% signals elite trap navigation; "
            "live-ball share of trap turnovers above 70% amplifies the cost."
        ),
        "mechanism": (
            "A well-timed double-team compresses the hub's passing window to under "
            "one second; handlers who slow-react or lack weak-hand passing ability "
            "are forced into held-ball or backward passes that defenders intercept."
        ),
        "conditions": (
            "Triggered by post-entry doubles and top-of-key blitzes on ball-screen "
            "actions; frequency rises in playoff settings where defensive coordinators "
            "dedicate the double-team resource specifically against high-usage hubs."
        ),
        "magnitude": (
            "Each trap turnover costs a full possession (~1.05 pts) and frequently "
            "results in a live-ball transition opportunity; improving from the "
            "bottom-third to median trap resistance saves roughly 1-2 possessions per game."
        ),
        "links": [
            "bad_pass_turnover_propensity",
            "pressure_induced_turnover_susceptibility",
            "team_turnover_economy_profile",
            "live_ball_turnover_share",
        ],
    },
    {
        "slug": "offensive_to_defensive_foul_balance",
        "title": "Foul-Mix Balance and Foul Economy",
        "summary": (
            "Captures whether a player's foul budget is spent on high-value rim "
            "deterrence or low-value perimeter and off-ball reaches, measured as "
            "the share of fouls that contest a shot versus non-shot fouls per 100 "
            "possessions."
        ),
        "stat_signature": (
            "Shot-contesting fouls as a share above 50% of total fouls indicates "
            "meaningful deterrence value; non-shot foul rate above 2.5 per 100 "
            "possessions flags economy waste; per-foul deterrence drops sharply "
            "below a 40% shot-contesting share."
        ),
        "mechanism": (
            "Fouls that contest a shot at least deliver deterrence information to "
            "the offensive player; non-shot fouls on screens and off-ball reaches "
            "add to the bonus clock with zero deterrence return, amplifying the "
            "free-throw cost per foul spent."
        ),
        "conditions": (
            "Most visible for mobile big men in switch-heavy schemes who foul "
            "both in post defense and on perimeter close-out duties; non-shot "
            "foul share rises as the role expands beyond the defensive specialty."
        ),
        "magnitude": (
            "A player with 50% non-shot foul share contributes roughly 40% fewer "
            "deterrence actions per foul budget dollar than a rim-focused defender; "
            "teams with poor foul economy reach the bonus 2-4 possessions earlier."
        ),
        "links": [
            "shooting_foul_propensity",
            "reach_in_perimeter_foul_rate",
            "off_ball_foul_leakage",
            "foul_trouble_aggression_tax",
        ],
    },
    {
        "slug": "foul_trouble_aggression_tax",
        "title": "Foul-Trouble Aggression Tax",
        "summary": (
            "Captures the measurable drop in defensive activity once a player carries "
            "foul trouble, measured as the decline in contest rate, deflections, and "
            "rim challenges after reaching the foul-out warning threshold."
        ),
        "stat_signature": (
            "Contest rate drops 15-25% after accumulating three first-half fouls; "
            "deflection rate declines 20-30% in restricted-play stints; "
            "post-threshold rim challenge frequency falls by roughly 0.8 per 100 "
            "possessions for primary rim protectors."
        ),
        "mechanism": (
            "Coaching instructions and player self-management reduce defensive "
            "aggression to preserve eligibility; opponents recognize the passivity "
            "and attack the troubled defender or the exposed lane."
        ),
        "conditions": (
            "Most consequential for primary rim protectors and defensive hubs; "
            "aggression tax appears within 1-2 possessions of the threshold in "
            "playoff games where foul-out stakes are highest."
        ),
        "magnitude": (
            "Lineup defensive rating worsens by 4-8 points per 100 possessions "
            "when the primary rim protector is in foul trouble; opponents shoot "
            "approximately 5-8% better at the rim during restricted-play stretches."
        ),
        "links": [
            "early_foul_accumulation_pace",
            "shooting_foul_propensity",
            "verticality_discipline_at_rim",
            "offensive_to_defensive_foul_balance",
        ],
    },
    {
        "slug": "turnover_recovery_response",
        "title": "Post-Turnover Transition-Defense Response",
        "summary": (
            "Captures how effectively a unit recovers after a giveaway to limit the "
            "resulting fast break, measured as transition points allowed per live-ball "
            "turnover and cross-match recovery rate after the giveaway."
        ),
        "stat_signature": (
            "League-average transition points per live-ball turnover ~1.1; "
            "elite recovery units hold below 0.85; cross-match recovery rate above "
            "70% within two seconds of the turnover signal organized transition defense."
        ),
        "mechanism": (
            "The player closest to the ball at the turnover must sprint back rather "
            "than pursue the ball; back-line defenders must communicate coverage "
            "instantly to outnumber the offensive wave before it sets up."
        ),
        "conditions": (
            "Most stressed when the turnover occurs in the offensive frontcourt and "
            "the defense has four players above the foul line; fatigue amplifies "
            "recovery failures in the fourth quarter."
        ),
        "magnitude": (
            "Moving from average to elite transition-defense-after-turnover quality "
            "saves roughly 0.25 points per live-ball turnover; over a typical season "
            "volume this corresponds to ~4-6 points per game saved."
        ),
        "links": [
            "live_ball_turnover_share",
            "team_turnover_economy_profile",
            "bad_pass_turnover_propensity",
        ],
    },
    {
        "slug": "team_turnover_economy_profile",
        "title": "Team Turnover-Economy Profile",
        "summary": (
            "Captures a lineup's structural giveaway rate from its action mix and ball "
            "movement, measured as team turnover percentage and the split between "
            "unforced execution errors and pressure-forced turnovers."
        ),
        "stat_signature": (
            "Team turnover percentage above 15.5% is structurally damaging; "
            "unforced share above 60% of total turnovers flags execution culture "
            "rather than defensive pressure as the driver; live-ball percentage above "
            "55% compounds the pace cost."
        ),
        "mechanism": (
            "Action-mix decisions (post-entry frequency, cross-court skip volume, "
            "pick-and-roll handler selection) structurally set the turnover floor; "
            "rotation-driven lineups with multiple hub handlers elevate this floor."
        ),
        "conditions": (
            "Most visible in fast-tempo offensive systems that prioritize ball "
            "movement over possession security; the profile is lineup-specific and "
            "shifts when a primary handler enters or exits."
        ),
        "magnitude": (
            "Each 1-percentage-point rise in team turnover rate corresponds to "
            "approximately 1.0-1.5 fewer offensive possessions per 48 minutes; "
            "over a season this compounds to roughly 80-120 offensive possessions lost."
        ),
        "links": [
            "live_ball_turnover_share",
            "turnover_recovery_response",
            "double_team_turnover_resistance",
            "bad_pass_turnover_propensity",
        ],
    },
]
