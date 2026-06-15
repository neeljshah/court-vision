"""scripts.platformkit.specs.dueloutcomes_soccer
Person-free Soccer DuelOutcomes concept spec — 18 dense contest nodes.
"""
from __future__ import annotations

SPORT = "Soccer"
FAMILY = "DuelOutcomes"

CONCEPTS: list[dict] = [
    {
        "slug": "aerial_duel_header_contest",
        "title": "Aerial Duel Header Contest",
        "summary": (
            "The contested-jump battle for a ball in the air, resolved by aerial duel "
            "win rate, jump-timing leverage, and first-contact direction toward retained "
            "possession. Winning aerial duels in defensive thirds correlates with "
            "suppressed headed-goal concessions."
        ),
        "stat_signature": (
            "Aerial duel win rate ≥55 % = above-average; teams winning >60 % of "
            "defending-third aerial duels concede headed goals at roughly half the rate "
            "of sub-50 % sides. First-contact retention (header controlled versus cleared) "
            "splits into productive (~30 %) and mere-clearance (~70 %) outcomes."
        ),
        "mechanism": (
            "Jump timing relative to ball apex determines physical leverage; the player "
            "arriving 0.1–0.2 s early pins the opponent below centre of gravity. "
            "Neck-muscle engagement at contact redirects ball spin, making angle-of-"
            "deflection predictable and directing the ball toward a teammate."
        ),
        "conditions": (
            "Emerges prominently on long-ball and set-piece deliveries, in weather "
            "reducing ground-passing reliability, and against sides with a deliberate "
            "route-one shape. Frequency rises in the final 15 minutes when tired "
            "defenders concede aerial contests near goal."
        ),
        "magnitude": (
            "A unit increase in aerial win rate from 50 % to 60 % corresponds to "
            "roughly 0.12–0.18 fewer headed goals conceded per match across a season "
            "sample; the effect is larger in central-zone contests than wide-flank ones."
        ),
        "links": [
            "set_piece_marking_jostle_duel",
            "high_ball_punch_versus_header_duel",
            "second_ball_knockdown_duel",
            "fifty_fifty_loose_ball_duel",
        ],
    },
    {
        "slug": "ground_duel_shoulder_charge",
        "title": "Ground Duel Shoulder-Charge Contest",
        "summary": (
            "The shoulder-to-shoulder battle for a rolling ball, measured by ground "
            "duel win rate and possession-retention percentage after legal contact. "
            "High ground-duel win rates in midfield are associated with compactness "
            "and territory control across half."
        ),
        "stat_signature": (
            "Ground duel win rate: elite defensive midfielders ≥58 %; average ~50 %. "
            "Possession retained after ground-duel win: ~62 % league average. "
            "Teams winning >55 % of ground duels across a match win possession battles "
            "in wide zones and generate more second-phase attacks."
        ),
        "mechanism": (
            "Hip-width stance and low centre of gravity maximise lateral force transfer "
            "in the shoulder charge, reducing the opponent's ability to accelerate away. "
            "Ball-side foot placement seals the angle; the legal charge displaces without "
            "elbowing, keeping the contest within the rules and preserving possession."
        ),
        "conditions": (
            "Most decisive on heavy or wet pitches where first-touch control is harder, "
            "and in congested central areas where space to avoid contact is limited. "
            "High-press sides trigger more ground duels in the opponent's defensive third."
        ),
        "magnitude": (
            "Ground duel win-rate advantage of 10 percentage points correlates with "
            "roughly 4–6 additional ball-possessions per match in the central corridor; "
            "territorial control index rises by ~5 % per match on average."
        ),
        "links": [
            "fifty_fifty_loose_ball_duel",
            "one_versus_one_take_on_duel",
            "pressing_trigger_ball_win_duel",
            "drop_off_delay_versus_dive_in_duel",
        ],
    },
    {
        "slug": "one_versus_one_take_on_duel",
        "title": "One-Against-One Take-On Duel",
        "summary": (
            "The dribbler-against-defender isolation battle, measured by take-on success "
            "rate, foul-drawn rate, and dispossession rate per attempted beat. Successful "
            "take-ons in wide areas generate crossing opportunities; central take-ons "
            "create shooting lanes inside the penalty area."
        ),
        "stat_signature": (
            "League-average take-on success rate: ~48–52 %. Rates above 60 % in wide "
            "channels correlate with cross-attempt volume 1.4× baseline. Foul drawn per "
            "10 take-on attempts: ~1.2 average; players in isolated wide zones draw fouls "
            "at 1.8× the rate of congested central zones."
        ),
        "mechanism": (
            "Deceptive body-feint shifts the defender's weight, creating a 0.3–0.5 s "
            "gap before the defender can re-balance. Accelerating into that gap exploits "
            "the momentum mismatch. Speed differential at the point of the drop-shoulder "
            "determines whether the dribbler clears the trailing leg."
        ),
        "conditions": (
            "Most frequent in wide channels and half-spaces when a team trails by one "
            "goal and seeks to manufacture crosses. Isolation patterns increase against "
            "high defensive lines that leave one-against-one situations in transition."
        ),
        "magnitude": (
            "A 10 pp improvement in take-on success rate in the attacking third adds "
            "roughly 0.8–1.2 additional cross attempts per match; expected-goal volume "
            "from open-play crosses rises proportionally."
        ),
        "links": [
            "ground_duel_shoulder_charge",
            "channel_running_body_position_duel",
            "tracking_run_recovery_sprint_duel",
            "drop_off_delay_versus_dive_in_duel",
        ],
    },
    {
        "slug": "last_man_tackle_recovery_duel",
        "title": "Last-Man Tackle Recovery Duel",
        "summary": (
            "The desperation containment battle when a defender confronts a through-ball "
            "runner as the final cover, measured by clean-tackle rate, shot-prevention "
            "rate, and foul-versus-recover tradeoff under high-stakes spatial pressure."
        ),
        "stat_signature": (
            "Clean-tackle rate on through-ball situations: ~42 % league average; concession "
            "rate on these chances: ~0.72 xG per attempt when defence is beaten. "
            "Foul-to-penalty conversion: ~76 % of professional-level fouls in the last-man "
            "scenario result in a penalty; recover-without-foul success ~35–40 %."
        ),
        "mechanism": (
            "The last defender angles toward the ball-side to reduce the attacker's shooting "
            "corridor while delaying the shot attempt. By forcing the attacker wide, the "
            "defender reduces shot angle and buys recovery time for covering teammates. "
            "Committing too early triggers the foul-penalty tradeoff."
        ),
        "conditions": (
            "Triggered when defensive line is bypassed by a through-pass or a counter-"
            "attack with numerical inferiority. Frequency rises in matches where one side "
            "presses high and is exposed on transitions, especially after set-piece "
            "attacking transitions."
        ),
        "magnitude": (
            "Clean recovery in the last-man scenario reduces the opponent xG from ~0.72 "
            "to ~0.25 per attempt; fouling concedes a penalty worth ~0.76 xG. The decision "
            "quality at this moment has outsized within-match expected-goal impact."
        ),
        "links": [
            "through_ball_offside_step_duel",
            "tracking_run_recovery_sprint_duel",
            "goalkeeper_one_versus_one_block_duel",
            "drop_off_delay_versus_dive_in_duel",
            "tackle_slide_timing_duel",
        ],
    },
    {
        "slug": "shielding_back_to_goal_hold_duel",
        "title": "Shielding Back-to-Goal Hold-Up Duel",
        "summary": (
            "The body-positioning battle where a forward shields a pressing defender, "
            "measured by hold-up retention rate, lay-off completion, and foul-drawn rate "
            "under back pressure. Effective hold-up play allows the team to advance "
            "midfield runners into support positions."
        ),
        "stat_signature": (
            "Hold-up retention rate (possession kept for ≥3 s while shielding): ~55–65 % "
            "for physical forwards. Lay-off completion to supporting runner: ~70 %. "
            "Foul drawn per 10 hold-up contests: ~1.4 average; rises to ~2.1 when the "
            "defender's arm position exceeds back-contact threshold."
        ),
        "mechanism": (
            "Wide stance and low hip position anchor the forward's body against the "
            "defender's force vector. Arms held outward within legal bounds create a "
            "physical barrier; the ball is screened between foot and body. Timing the "
            "lay-off precisely as the defender over-commits triggers fouls or release."
        ),
        "conditions": (
            "Appears frequently in direct-play systems targeting a target forward, in "
            "transitions from defence, and in congested midfield zones where possession "
            "recycling depends on a focal outlet. Heavy pressing shapes maximise frequency."
        ),
        "magnitude": (
            "Sides with high hold-up retention rates sustain 1.5–2.5 additional multi-"
            "pass sequences per match in the attacking half; forward presence draws "
            "defenders and opens space for arriving midfielders."
        ),
        "links": [
            "ground_duel_shoulder_charge",
            "second_ball_knockdown_duel",
            "pressing_trigger_ball_win_duel",
            "fifty_fifty_loose_ball_duel",
        ],
    },
    {
        "slug": "fifty_fifty_loose_ball_duel",
        "title": "Fifty-Fifty Loose-Ball Duel",
        "summary": (
            "The simultaneous-arrival battle for a contested loose ball, measured by "
            "loose-ball recovery rate per contest and second-ball win percentage. "
            "Teams that dominate loose-ball duels sustain attacking momentum and limit "
            "opponent counter-attack transitions."
        ),
        "stat_signature": (
            "Loose-ball recovery rate: varies 45–58 % by side; teams above 54 % win "
            "~3–4 more possessions per match. Second-ball win rate following aerial "
            "contests: ~52 % for sides with organised recovery shape, ~44 % for "
            "disorganised shapes."
        ),
        "mechanism": (
            "Anticipating the rebound trajectory from a clearance or aerial contest "
            "allows a player to arrive at the fall zone before the opponent. First-"
            "mover advantage in the 50-50 is determined by prediction rather than pure "
            "speed; reading spin and deflection angle is the primary skill."
        ),
        "conditions": (
            "Occurs in midfield after long clearances, at the second phase of set pieces, "
            "and following goalkeeper punches or deflections. High frequency in direct-"
            "play matches and in matches where both sides press the clearance trigger."
        ),
        "magnitude": (
            "A 5 pp advantage in loose-ball recovery rate correlates with roughly 2 "
            "additional attacking transitions per match; territory gained on second balls "
            "shifts average attack starting position by ~8 metres upfield."
        ),
        "links": [
            "aerial_duel_header_contest",
            "second_ball_knockdown_duel",
            "post_clearance_second_phase_duel",
            "ground_duel_shoulder_charge",
        ],
    },
    {
        "slug": "pressing_trigger_ball_win_duel",
        "title": "Pressing-Trigger Ball-Win Duel",
        "summary": (
            "The press-against-controlled-touch battle on a pressed receiver, measured "
            "by ball-recovery rate within five seconds and turnover-to-shot conversion "
            "after the win. Effective press-triggers generate high-value turnovers in "
            "advanced positions."
        ),
        "stat_signature": (
            "Ball recovery within 5 s of press trigger: ~28–38 % across top leagues. "
            "Turnover-to-shot conversion when recovered in the attacking third: ~22 %. "
            "xG per press-triggered turnover near the opponent's box: ~0.08 average."
        ),
        "mechanism": (
            "The pressing trigger — typically a poor first touch or backward pass — "
            "signals the press shape to collapse toward the ball. The front presser "
            "reduces the receiver's time on the ball below the ~1.5 s threshold needed "
            "for a controlled exit pass, forcing an error or a panicked clearance."
        ),
        "conditions": (
            "Most potent against build-up shapes with slow ball circulation and sides "
            "with centre-backs of limited passing range under pressure. Frequency rises "
            "in the first 20 minutes when pressed sides haven't established rhythm."
        ),
        "magnitude": (
            "Sides that trigger recoveries in the opponent's defensive third generate "
            "roughly 0.3–0.5 additional xG per match from press-derived chances; the "
            "effect diminishes sharply when recovery occurs beyond 30 m from goal."
        ),
        "links": [
            "cover_shadow_lane_block_duel",
            "ground_duel_shoulder_charge",
            "drop_off_delay_versus_dive_in_duel",
            "one_versus_one_take_on_duel",
        ],
    },
    {
        "slug": "tracking_run_recovery_sprint_duel",
        "title": "Tracking-Run Recovery-Sprint Duel",
        "summary": (
            "The foot-race between an overlapping attacker and a recovering defender, "
            "measured by recovery-arrival rate before the box and shot-prevention "
            "percentage on tracked runs. Speed differential and starting-position "
            "advantage determine the outcome."
        ),
        "stat_signature": (
            "Recovery arrival before the penalty area: ~58 % of tracked sprints in "
            "top-flight data. Shot prevention when defender recovers: ~62 %; when "
            "outpaced: ~18 %. Average sprint duels cover 20–35 m within 4–5 s."
        ),
        "mechanism": (
            "The attacker's head-start after splitting the line forces the defender "
            "into maximum sprint effort from a standing recovery position. The deficit "
            "compounds if the attacker angles diagonally — forcing the defender to "
            "chase a curved path rather than a straight closing line."
        ),
        "conditions": (
            "Emerges on counter-attacks following midfield turnovers, on long-switch "
            "passes catching a full-back out of position, and in transitions after "
            "failed attacking set pieces. High-line defences produce more sprint duels "
            "from through-ball breaks."
        ),
        "magnitude": (
            "When attacker wins the sprint duel, the resulting chance carries "
            "~0.18–0.25 xG on average; defender arrival within 2 m of the shot reduces "
            "xG by roughly 35 % by narrowing angle and increasing pressure."
        ),
        "links": [
            "last_man_tackle_recovery_duel",
            "through_ball_offside_step_duel",
            "one_versus_one_take_on_duel",
            "goalkeeper_one_versus_one_block_duel",
        ],
    },
    {
        "slug": "set_piece_marking_jostle_duel",
        "title": "Set-Piece Marking Jostle Duel",
        "summary": (
            "The pre-delivery grappling battle inside the box on a dead ball, measured "
            "by first-contact win rate and clean-header conversion under marking contact. "
            "Delivery-timed runs that shed markers produce higher-xG headed attempts."
        ),
        "stat_signature": (
            "First-contact win rate at corners: ~55 % for the defending team. "
            "Headed attempts on target from set pieces: ~28 % conversion to shot, ~9 % "
            "to goal. Clean-header xG (~0.15) exceeds contested-header xG (~0.07) "
            "by roughly 2×."
        ),
        "mechanism": (
            "Holding contact in the box slows the runner; a mid-run shoulder check "
            "forces the attacker onto the wrong foot at the moment of the delivery. "
            "Movement deception — near-post decoy drawing the marker before a far-post "
            "dart — exploits the defender's commitment to the wrong trajectory."
        ),
        "conditions": (
            "Manifests on corner kicks, direct free kicks within 30 m, and long "
            "throw-ins into the box. Frequency and intensity increase in matches "
            "where one side has a physical aerial advantage and seeks to exploit it."
        ),
        "magnitude": (
            "Teams winning the marking jostle to create clean headers score from set "
            "pieces at roughly 1.3–1.7× the rate of sides that generate only contested "
            "headers; total set-piece xG differential of ~0.10–0.15 per match."
        ),
        "links": [
            "aerial_duel_header_contest",
            "high_ball_punch_versus_header_duel",
            "throw_in_first_contact_duel",
            "wide_channel_cross_block_duel",
        ],
    },
    {
        "slug": "through_ball_offside_step_duel",
        "title": "Through-Ball Offside-Step Duel",
        "summary": (
            "The line-timing battle between a runner's break and a defensive line's "
            "step-up, measured by onside-break success rate and offside-trap trigger "
            "frequency. Precise collective step-up nullifies through-ball attacks; "
            "mistimed steps gift clear goalscoring situations."
        ),
        "stat_signature": (
            "Offside trap success rate: ~60–68 % for organised high-line defences; "
            "~38 % for low-block sides attempting late step-ups. Onside breaks per "
            "match on through balls: ~3–5 in high-press contexts. Clear-chance "
            "concession when trap fails: ~0.35 xG per incident."
        ),
        "mechanism": (
            "Defenders must step simultaneously on the passer's foot-contact with the "
            "ball; any defender lagging by ≥0.3 s creates an onside gap. The attacker "
            "times the run to the last moment before contact, exploiting the line's "
            "latency in collective communication and spatial coordination."
        ),
        "conditions": (
            "High-line shapes generate the most offside-duel incidents. Frequency "
            "rises against sides with fast forwards adept at precise run timing and "
            "on artificial surfaces where ball pace increases pass speed."
        ),
        "magnitude": (
            "A 10 pp increase in trap success rate reduces opponent clear-chance "
            "creation from through balls by ~1.5 per match; failed traps account "
            "for roughly 0.10–0.18 additional xG conceded per match on average."
        ),
        "links": [
            "last_man_tackle_recovery_duel",
            "tracking_run_recovery_sprint_duel",
            "goalkeeper_one_versus_one_block_duel",
            "channel_running_body_position_duel",
        ],
    },
    {
        "slug": "goalkeeper_one_versus_one_block_duel",
        "title": "Goalkeeper One-Against-One Block Duel",
        "summary": (
            "The narrowing-angle battle when a keeper confronts a through-on attacker, "
            "measured by save rate on clear-through chances and spread-block shot-"
            "blocking percentage. Aggressive narrowing reduces the attacker's available "
            "goal target by two-thirds."
        ),
        "stat_signature": (
            "Save rate on clear one-on-one situations: ~35–42 % across top leagues. "
            "Spread-block saves (legs/feet): ~22 % of one-on-one saves. Expected goal "
            "for the attacker from a clear one-on-one: ~0.38–0.46 xG depending on "
            "distance and angle."
        ),
        "mechanism": (
            "The keeper closes down at controlled pace to set the spread position "
            "before the attacker decides to shoot, reducing the visible goal target "
            "to <30 % of full width from 10 m. Early commitment risks the dink; "
            "remaining on the line concedes the full target. Timing the spread to "
            "the attacker's hip angle at shot preparation is the core skill."
        ),
        "conditions": (
            "Arises on successful through-ball breaks and counter-attacks where the "
            "defensive recovery sprint duel is lost. Frequency directly proportional "
            "to how aggressively the defensive line plays offside."
        ),
        "magnitude": (
            "An elite narrowing save rate (>45 %) reduces xG-to-goal conversion from "
            "one-on-one situations by ~0.10–0.12 per match relative to an average "
            "keeper; spread-block positioning determines ~60 % of the save probability."
        ),
        "links": [
            "last_man_tackle_recovery_duel",
            "tracking_run_recovery_sprint_duel",
            "high_ball_punch_versus_header_duel",
            "through_ball_offside_step_duel",
        ],
    },
    {
        "slug": "high_ball_punch_versus_header_duel",
        "title": "High-Ball Punch-Against-Header Duel",
        "summary": (
            "The contested-claim battle in the box between a keeper coming to punch "
            "and attackers attacking a cross, measured by claim success rate and "
            "conceded-from-aerial frequency. Decisive keeper claims remove dangerous "
            "aerial contests; poor claims gift second-phase shots."
        ),
        "stat_signature": (
            "Keeper claim success rate on crossed deliveries: ~65–72 % for commanding "
            "keepers; ~48 % for hesitant ones. Conceded-from-aerial frequency after "
            "failed punch: ~0.09 xG per incident. Clean punch clearance distance: "
            "12–18 m average."
        ),
        "mechanism": (
            "The keeper must decide to claim or punch at the moment the cross leaves "
            "the delivery foot. Claiming requires two-hand grip under body-contact "
            "laws; punching sacrifices possession but clears the immediate danger zone. "
            "Hesitation — neither committed claim nor punch — creates the contested "
            "flick-on that attackers exploit."
        ),
        "conditions": (
            "Peaks during sustained crossing attacks from wide areas and on set-piece "
            "deliveries from the flank. Keeper indecision increases when central "
            "defenders screen the ball-flight path late."
        ),
        "magnitude": (
            "Keepers with claim rates above 70 % concede from aerial sources at roughly "
            "half the rate of sub-50 % claim sides; each failed punch generates a second-"
            "phase contest with ~0.09 xG on average."
        ),
        "links": [
            "aerial_duel_header_contest",
            "set_piece_marking_jostle_duel",
            "goalkeeper_one_versus_one_block_duel",
            "second_ball_knockdown_duel",
        ],
    },
    {
        "slug": "tackle_slide_timing_duel",
        "title": "Slide-Tackle Timing Duel",
        "summary": (
            "The commit-timing battle of a sliding challenge against a moving ball, "
            "measured by clean-ball-win rate on slides and foul-or-card rate per "
            "attempt. Mistimed slides produce fouls; perfectly timed slides recover "
            "possession and preserve defensive shape."
        ),
        "stat_signature": (
            "Clean-ball-win rate on slide tackles: ~48–56 % across top leagues. "
            "Foul rate per slide attempt: ~22 %. Yellow-card rate per 10 slide "
            "fouls: ~28 %. Clean slide recovery results in a retained possession "
            "~58 % of the time."
        ),
        "mechanism": (
            "The defender must commit when the ball is between the dribbler's strides, "
            "with foot directed at the ball rather than the player's ankle. Approach "
            "angle of 30–45 degrees maximises ball-contact likelihood while minimising "
            "dangerous-challenge trajectory. Arriving too early clips the player's "
            "standing leg; too late deflects off the ball to the dribbler's benefit."
        ),
        "conditions": (
            "Occurs most often in wide defensive zones after a take-on situation and "
            "in desperate last-ditch recovery scenarios near the penalty area. Frequency "
            "increases on wet pitches where the sliding range extends."
        ),
        "magnitude": (
            "Clean slides in the defensive third prevent shots at an ~0.18 xG-per-"
            "prevented-chance rate; foul-concession in the penalty area risks a penalty "
            "worth ~0.76 xG, making disciplined slide timing the highest-leverage "
            "contest-level decision."
        ),
        "links": [
            "last_man_tackle_recovery_duel",
            "drop_off_delay_versus_dive_in_duel",
            "ground_duel_shoulder_charge",
            "one_versus_one_take_on_duel",
        ],
    },
    {
        "slug": "drop_off_delay_versus_dive_in_duel",
        "title": "Delay-Against-Dive-In Defending Duel",
        "summary": (
            "The decision battle where a defender either jockeys to delay or commits "
            "to a tackle against a runner, measured by delay-induced support-arrival "
            "rate and beaten-on-commit frequency. Jockeying to buy time for cover is "
            "often superior to attempting an early tackle in space."
        ),
        "stat_signature": (
            "Support arrival within 3 s when defender jockeys: ~65 % of situations. "
            "Beaten-on-commit rate in open space (>6 m from goal): ~38 %. Delay "
            "success (runner slowed until cover arrives without conceding a shot): "
            "~57 % of jockey situations."
        ),
        "mechanism": (
            "Jockeying forces the attacker to carry the ball wider or slower, reducing "
            "forward momentum while covering teammates track back. The defender stays "
            "goal-side and ball-side simultaneously, cutting off the central lane. "
            "Diving in transfers momentum advantage to the attacker if the tackle "
            "is beaten."
        ),
        "conditions": (
            "Most critical in transition where a single defender faces an attacker in "
            "open space with no immediate cover. Also common in one-against-one wide "
            "channel situations where the full-back must decide whether to press or "
            "contain pending midfield recovery."
        ),
        "magnitude": (
            "Successful delay in open-space scenarios reduces opponent shot probability "
            "within 10 s from ~32 % to ~14 %; the cover-arrival mechanism is the "
            "primary defensive shape restoration tool in transition."
        ),
        "links": [
            "one_versus_one_take_on_duel",
            "tackle_slide_timing_duel",
            "last_man_tackle_recovery_duel",
            "pressing_trigger_ball_win_duel",
        ],
    },
    {
        "slug": "cover_shadow_lane_block_duel",
        "title": "Cover-Shadow Lane-Block Duel",
        "summary": (
            "The body-angle battle where a presser screens a passing lane to force "
            "play to a side, measured by forced-direction success rate and turnover "
            "induction on shadowed receivers. Correct cover-shadow body positioning "
            "channels opponents into the press trap."
        ),
        "stat_signature": (
            "Forced-direction success rate (pass channelled to predetermined side): "
            "~55–65 % for coordinated pressing units. Turnover induction rate on "
            "shadowed receivers: ~20–25 % within the pressing structure. Ball "
            "recovery within 6 s after forced-direction: ~32 %."
        ),
        "mechanism": (
            "The presser positions hip-angle to open one passing lane while closing the "
            "other with body orientation rather than foot position, making the desired "
            "pass invisible to the ball-carrier's peripheral vision. The receiving "
            "teammate of the forced pass is met by a pre-positioned second presser "
            "completing the trap."
        ),
        "conditions": (
            "Central to coordinated pressing systems that pre-assign cover-shadow duties "
            "before the ball arrives. Most effective against sides that rely on a specific "
            "central distributor as their primary exit route."
        ),
        "magnitude": (
            "Units with high forced-direction success channel ~3–4 additional pressured "
            "passes per match into the pre-planned trap zone; turnover-to-chance "
            "conversion from these recoveries averages ~0.06 xG per recovery."
        ),
        "links": [
            "pressing_trigger_ball_win_duel",
            "ground_duel_shoulder_charge",
            "drop_off_delay_versus_dive_in_duel",
            "channel_running_body_position_duel",
        ],
    },
    {
        "slug": "second_ball_knockdown_duel",
        "title": "Second-Ball Knockdown Duel",
        "summary": (
            "The positioning battle to win the drop from a flick-on or knockdown, "
            "measured by second-ball recovery rate around aerial contests and territory "
            "gain on the win. Anticipating flick-on trajectories determines second-"
            "phase superiority."
        ),
        "stat_signature": (
            "Second-ball recovery rate: ~52 % for organised supporting runners, ~44 % "
            "for disorganised sides. Territory gain when second ball is won in the "
            "opponent's defensive third: ~12–18 m average upfield. Second-ball shot "
            "creation rate: ~15 % of attacking-third wins generate a shot."
        ),
        "mechanism": (
            "Flick-on direction from an aerial contest is partially predictable from the "
            "near-post/far-post approach angle of the header. Supporting runners who read "
            "this trajectory pre-position at the expected drop zone rather than chasing "
            "the primary aerial contest, arriving first at the fallen ball."
        ),
        "conditions": (
            "Occurs systematically after long-ball entries, goal kicks under pressure, "
            "and set-piece first-phase contacts. Direct-play sides generate the most "
            "second-ball situations per match."
        ),
        "magnitude": (
            "Teams winning second balls at ≥55 % generate ~2 additional attacking "
            "sequences per match from these situations; the compounding effect of "
            "sustained second-ball dominance shifts average territory by 5–8 m per half."
        ),
        "links": [
            "aerial_duel_header_contest",
            "fifty_fifty_loose_ball_duel",
            "post_clearance_second_phase_duel",
            "shielding_back_to_goal_hold_duel",
        ],
    },
    {
        "slug": "channel_running_body_position_duel",
        "title": "Channel-Running Body-Position Duel",
        "summary": (
            "The half-space leverage battle as a runner attacks between defenders, "
            "measured by inside-shoulder win rate and chance-creation frequency from "
            "channel breaks. Winning the body-position contest in the channel unlocks "
            "diagonal crossing and cut-back opportunities."
        ),
        "stat_signature": (
            "Inside-shoulder win rate in channel runs: ~52 % for attacking sides in "
            "top leagues. Chance-creation from successful channel breaks: ~0.12 xG "
            "per break on average. Cross completion from won channel positions: ~38 % "
            "versus ~22 % from blocked channel entries."
        ),
        "mechanism": (
            "The runner leads with the inside shoulder to gain the space between the "
            "centre-back and full-back, forcing the defender to either block with the "
            "arm (foul risk) or track wider (ceding the run). Ball delivery into the "
            "channel must be timed to the runner's second stride for optimal reception."
        ),
        "conditions": (
            "Exploited by runners against narrow defensive mid-blocks that leave "
            "channel space open and against wide defenders who fail to communicate "
            "with central defenders on runner-handover responsibilities."
        ),
        "magnitude": (
            "Sides exploiting channel runs generate ~1.5 additional crossing situations "
            "per match from these positions; channel-break chance quality (~0.12 xG) "
            "exceeds static wide-cross quality (~0.07 xG) by roughly 70 %."
        ),
        "links": [
            "one_versus_one_take_on_duel",
            "tracking_run_recovery_sprint_duel",
            "through_ball_offside_step_duel",
            "cover_shadow_lane_block_duel",
        ],
    },
    {
        "slug": "post_clearance_second_phase_duel",
        "title": "Post-Clearance Second-Phase Duel",
        "summary": (
            "The reorganisation battle to win the next ball after a defensive clearance, "
            "measured by second-phase recovery rate and sustained-pressure concession "
            "frequency. Teams that win second phases after clearances relieve sustained "
            "pressure and restore defensive shape."
        ),
        "stat_signature": (
            "Second-phase recovery rate after defensive clearance: ~50 % at league "
            "average; organised defensive blocks recover ~57 %. Sustained-pressure "
            "concession (shot within 6 s of clearance due to lost second phase): "
            "~18 % of cases when second ball is lost."
        ),
        "mechanism": (
            "Clearances under pressure produce unpredictable trajectories; teams that "
            "designate a defensive midfielder to contest the second ball and attacking "
            "midfielders to press the rebound zone win these duels through collective "
            "positional pre-occupation rather than individual reaction."
        ),
        "conditions": (
            "Occurs continuously in matches where one side has territorial dominance "
            "and sustained possession in the attacking third. Direct-play matches "
            "generate the most post-clearance duels per 90 minutes."
        ),
        "magnitude": (
            "Teams winning second-phase duels at ≥55 % clear their defensive third "
            "possession after ~2 exchanges; losing the second phase sustains opponent "
            "possession averaging 1.8 additional shots per match from retained pressure."
        ),
        "links": [
            "fifty_fifty_loose_ball_duel",
            "second_ball_knockdown_duel",
            "aerial_duel_header_contest",
            "ground_duel_shoulder_charge",
        ],
    },
]
