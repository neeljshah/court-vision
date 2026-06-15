"""NBA PredictabilityTendencies spec — how predictable a team's play-calling,
tendencies, and decision patterns are, and the entropy of their choices.

Person-free, descriptive intelligence; no edge/ROI/pick claims.
"""
from __future__ import annotations

SPORT = "NBA"
FAMILY = "PredictabilityTendencies"

CONCEPTS: list[dict] = [
    {
        "slug": "play_call_entropy_after_timeout",
        "title": "Play-Call Entropy After Timeout",
        "summary": (
            "Measures the diversity of offensive actions run immediately following a "
            "timeout, capturing whether a coaching staff cycles through a wide range "
            "of set plays or repeatedly returns to a narrow action library."
        ),
        "stat_signature": (
            "Shannon entropy of post-timeout first-action type (pick-and-roll, isolation, "
            "spot-up, cut, post) below 1.2 bits signals high predictability; "
            "league-average entropy ~1.6 bits; teams below 1.0 rely on one or two "
            "actions for more than 60% of post-timeout possessions."
        ),
        "mechanism": (
            "Coaching staffs default to highest-confidence sets under time pressure, "
            "compressing the play-call distribution; defenses that scout the tendency "
            "pre-load personnel and coverage for the expected action, reducing the "
            "offensive team's information advantage."
        ),
        "conditions": (
            "Predictability peaks in fourth-quarter timeouts with a possession differential "
            "under five points, when coaches prioritize reliability over disguise; "
            "also elevated in elimination contexts where play-call variance is consciously "
            "sacrificed for execution certainty."
        ),
        "magnitude": (
            "High-entropy post-timeout offenses score roughly 1.08-1.15 points per "
            "possession on the ensuing sequence; low-entropy units below 1.0 bits "
            "average 0.90-0.98, a gap of 0.10-0.18 per possession on these high-stakes "
            "moments."
        ),
        "links": [
            "ato_set_predictability",
            "late_clock_action_repetition",
            "situational_substitution_pattern",
            "tendency_disguise_capacity",
        ],
    },
    {
        "slug": "first_option_isolation_predictability",
        "title": "First-Option Isolation Predictability",
        "summary": (
            "Captures how often a team's primary ball-handler receives a direct "
            "isolation possession as the first scripted action, and how reliably "
            "defenses can anticipate that routing decision before the ball advances "
            "past half-court."
        ),
        "stat_signature": (
            "Isolation frequency as first action above 35% of half-court possessions "
            "signals high routing predictability; first-option routing entropy below "
            "1.4 bits across play-type categories flags over-reliance on one initiator; "
            "tendency rises above 50% in clutch-minute samples for concentrated offenses."
        ),
        "mechanism": (
            "Personnel groupings and ball placement telegraph the intended hub before "
            "the defense must commit; defenses identify the primary initiator's location "
            "and send scripted double coverage or hard hedge before the catch, "
            "eliminating the tactical surprise the isolation was designed to exploit."
        ),
        "conditions": (
            "Most exploitable against switching defenses that can pre-load traps "
            "once the routing is read; less exploitable in early shot-clock sequences "
            "where the isolation is embedded inside motion that obscures the trigger."
        ),
        "magnitude": (
            "Teams with above-85th-percentile isolation-first-action rates allow "
            "defensive coordinators to allocate a second defender to the primary hub "
            "on roughly 25-30% of possessions; expected points per isolation attempt "
            "drop by 0.08-0.12 when the defense anticipates versus reacts."
        ),
        "links": [
            "play_call_entropy_after_timeout",
            "hot_hand_feeding_predictability",
            "counter_action_absence",
            "tendency_disguise_capacity",
        ],
    },
    {
        "slug": "pick_and_roll_tendency_telegraphing",
        "title": "Pick-and-Roll Tendency Telegraphing",
        "summary": (
            "Captures the degree to which the handler's dribble approach angle, "
            "the screener's setup position, and the timing of the action predict "
            "which read the offense will execute, reducing the defensive coverage "
            "choice to a binary pre-committed call."
        ),
        "stat_signature": (
            "Ball-screen action entropy across outcomes (pocket pass, pull-up, roll "
            "finish, kick-out) below 1.5 bits indicates telegraphing; screener "
            "location variance under 1.5 feet from the same two spots on 70%+ of "
            "actions is a measurable tell; tendency spikes when the unit runs the "
            "same coverage on 80%+ of first-action ball-screens."
        ),
        "mechanism": (
            "Repetitive screener placement and handler approach angle pre-expose "
            "the preferred read before the coverage must commit; drop or switch "
            "decisions become deterministic for the defense when the angle predicts "
            "the handler's pull-up tendency with above-70% accuracy."
        ),
        "conditions": (
            "Telegraphing costs most against film-prepared defenses in playoff contexts "
            "where coordinator preparation is maximized; less costly early in a series "
            "or in regular-season games where opponent scouting depth is shallower."
        ),
        "magnitude": (
            "When the defensive coverage decision is pre-committed based on the "
            "telegraphed angle, ball-screen efficiency drops by approximately 0.06-0.10 "
            "points per possession relative to unprepared coverage baselines; "
            "the effect compounds across a seven-game series."
        ),
        "links": [
            "play_call_entropy_after_timeout",
            "side_of_floor_preference_tendency",
            "counter_action_absence",
            "defensive_coverage_predictability",
        ],
    },
    {
        "slug": "late_clock_action_repetition",
        "title": "Late-Shot-Clock Action Repetition",
        "summary": (
            "Captures whether a team returns to the same finisher and action type "
            "when the shot clock falls below eight seconds, measuring the concentration "
            "of usage onto one player in desperation possessions."
        ),
        "stat_signature": (
            "Hub usage share above 55% in possessions with fewer than eight seconds "
            "remaining signals high repetition; first-action type entropy below 1.1 bits "
            "in late-clock situations indicates a scripted fallback; occurrence rate "
            "above 18% of half-court possessions creates a predictable exploitation window."
        ),
        "mechanism": (
            "Time pressure narrows the action space to the best creator, removing "
            "motion and misdirection; defenses pre-load a second defender toward the "
            "anticipated receiver and cut off the first drive angle, "
            "converting the desperation possession into a contested off-balance attempt."
        ),
        "conditions": (
            "Maximally predictable in the fourth quarter when defenses extend "
            "possessions deliberately to manufacture late-clock entropy; less "
            "predictable in fast-tempo offenses that reach late-clock from motion "
            "rather than a designed isolation."
        ),
        "magnitude": (
            "Point-per-possession in late-clock possessions averages 0.72-0.82 league-wide; "
            "teams whose late-clock action is well-scouted fall to 0.60-0.70, "
            "a material degradation on a possession type that occurs three to five "
            "times per game."
        ),
        "links": [
            "play_call_entropy_after_timeout",
            "first_option_isolation_predictability",
            "fourth_quarter_shot_distribution_narrowing",
            "counter_action_absence",
        ],
    },
    {
        "slug": "ato_set_predictability",
        "title": "After-Timeout Set Predictability",
        "summary": (
            "Measures the narrow set repertoire most teams deploy in the immediate "
            "possession following a called timeout, capturing the gap between the "
            "full-game play-call distribution and the contracted post-timeout distribution."
        ),
        "stat_signature": (
            "Post-timeout action-type concentration above 55% on a single play category "
            "is a predictability flag; ratio of post-timeout entropy to full-game "
            "entropy below 0.70 indicates significant contraction; "
            "tendencies stable within a coaching staff across a three-season span."
        ),
        "mechanism": (
            "Timeouts allow the defensive coordinator to communicate a targeted coverage "
            "for the expected set; when the offense runs the same inbound or half-court "
            "action the defense diagrammed in the huddle, the coverage is matched "
            "before the first dribble rather than reacted to after."
        ),
        "conditions": (
            "Most consequential in one-possession games in the final two minutes; "
            "concentration is heightened when the team's secondary creators are "
            "limited and the scripted set must reach the primary hub."
        ),
        "magnitude": (
            "ATO possessions where the defense correctly anticipates the set score "
            "approximately 0.08-0.12 fewer points than unanticipated ATO sets; "
            "across a season this accounts for roughly 8-15 possession-equivalents "
            "of value lost to telegraphing."
        ),
        "links": [
            "play_call_entropy_after_timeout",
            "inbound_action_tell",
            "tendency_disguise_capacity",
            "situational_substitution_pattern",
        ],
    },
    {
        "slug": "inbound_action_tell",
        "title": "Inbound-Action Tell",
        "summary": (
            "Captures the degree to which sideline and baseline inbound formations "
            "reliably predict the target receiver and primary action, giving the "
            "defense pre-catch knowledge of the intended play."
        ),
        "stat_signature": (
            "Inbound target concentration above 60% to a single receiver from "
            "baseline sets is a tell; inbound action entropy across target positions "
            "below 1.3 bits indicates limited deception; formation-to-action prediction "
            "accuracy above 65% is measurable from film charting."
        ),
        "mechanism": (
            "Inbound formations constrain the passing angle and screener geometry "
            "to a small number of reads; when the formation reliably precedes the "
            "same action, the defense aligns its denial before the ball is released, "
            "collapsing the initial advantage of the designed play."
        ),
        "conditions": (
            "Most predictable on end-of-half baseline inbounds when the set is "
            "designed for a specific receiver; less predictable in regular sideline "
            "inbounds where the defense cannot risk full denial of secondary options."
        ),
        "magnitude": (
            "Defenses that correctly pre-read an inbound set reduce the probability "
            "of a clean catch and immediate shot opportunity by an estimated 20-30%; "
            "over ten inbound possessions per game, this translates to roughly "
            "0.06-0.10 fewer expected points per inbound possession."
        ),
        "links": [
            "ato_set_predictability",
            "play_call_entropy_after_timeout",
            "situational_substitution_pattern",
            "tendency_disguise_capacity",
        ],
    },
    {
        "slug": "shot_location_entropy",
        "title": "Shot-Location Entropy",
        "summary": (
            "Captures how evenly a team distributes its field-goal attempts across "
            "the court zones — restricted area, mid-range, corner three, above-break "
            "three — and how predictable the zone weighting is from possession context."
        ),
        "stat_signature": (
            "Shot-location entropy below 1.5 bits across five court zones indicates "
            "a concentrated attack; corner-three plus restricted-area share above 75% "
            "combined is a modern efficiency concentration but also a scoutable pattern; "
            "mid-range share below 5% signals a binary attack defenses can prepare for."
        ),
        "mechanism": (
            "Highly concentrated shot profiles allow defenses to position off-ball "
            "defenders in denial zones tuned to the known distribution; the offense "
            "saves possessions going to the statistically optimal zones but surrenders "
            "the positioning advantage that shot-location unpredictability creates."
        ),
        "conditions": (
            "Predictability costs most when the defense has personnel specifically "
            "suited to protect the concentrated zone; less costly when the team's "
            "efficiency in the preferred zones is so high that deterrence fails anyway."
        ),
        "magnitude": (
            "Teams in the bottom quartile of shot-location entropy allow defenses "
            "to commit a rim protector and corner-coverage defender without "
            "mid-range respect, yielding roughly 0.03-0.06 fewer points per "
            "possession versus teams whose distribution forces multiple coverage modes."
        ),
        "links": [
            "side_of_floor_preference_tendency",
            "fourth_quarter_shot_distribution_narrowing",
            "counter_action_absence",
            "pick_and_roll_tendency_telegraphing",
        ],
    },
    {
        "slug": "personnel_driven_tendency_leakage",
        "title": "Personnel-Driven Tendency Leakage",
        "summary": (
            "Captures how reliably the on-court lineup combination predicts the "
            "offensive action type, giving defenses a tendencies map keyed to "
            "personnel groupings before the ball even advances."
        ),
        "stat_signature": (
            "Action-type entropy conditional on lineup combination below 1.4 bits "
            "signals that the personnel grouping leaks the play; specific five-man "
            "units with a dominant action share above 50% appear in roughly "
            "30-40% of NBA teams' most-used lineups."
        ),
        "mechanism": (
            "Lineup compositions telegraph their preferred action because role "
            "assignments within the unit naturally bias toward certain plays; "
            "a unit with three spot-up shooters signals drive-and-kick intent, "
            "and a unit with a dedicated screener signals ball-screen frequency."
        ),
        "conditions": (
            "Leakage is most harmful in late-game lineup decisions where the "
            "coaching staff inserts a specialist group whose action type is known; "
            "less harmful in balanced lineups where multiple action types are equally viable."
        ),
        "magnitude": (
            "Conditional on identifying the leaked personnel tendency, defenses "
            "achieve pre-matched coverage on an estimated 20-25% of possessions; "
            "over a full game this represents a coverage advantage on five to eight "
            "possessions where the offense's surprise factor is eliminated."
        ),
        "links": [
            "play_call_entropy_after_timeout",
            "situational_substitution_pattern",
            "tendency_disguise_capacity",
            "first_option_isolation_predictability",
        ],
    },
    {
        "slug": "situational_substitution_pattern",
        "title": "Situational Substitution Pattern",
        "summary": (
            "Captures the regularity with which a coaching staff makes specific "
            "substitutions at predictable game junctures — score differential, "
            "quarter boundaries, foul counts — allowing the opponent to anticipate "
            "lineup changes before they occur."
        ),
        "stat_signature": (
            "Substitution entropy by game situation below 1.3 bits across five "
            "trigger conditions signals high pattern regularity; lineup-entry timing "
            "predictability above 70% accuracy (within ±30 seconds) is measurable "
            "from charting; first-foul bench trigger used above 80% of the time "
            "represents a hard pattern."
        ),
        "mechanism": (
            "Coaches develop systematic substitution triggers for reliability and "
            "rest management; opponents who chart these triggers can time offensive "
            "attacks to target specific matchups, adjust defensive schemes ahead "
            "of an incoming lineup, or call timeouts to counter the change."
        ),
        "conditions": (
            "Most exploitable in playoff series where the opponent has three to seven "
            "games of charting data; also meaningful at quarter boundaries where "
            "the timing pattern is especially consistent across a season."
        ),
        "magnitude": (
            "Teams with highly predictable substitution timing face an estimated "
            "one to two extra correctly-timed offensive attacks per game targeting "
            "the newly-entered lineup's defensive weaknesses in its first two possessions."
        ),
        "links": [
            "play_call_entropy_after_timeout",
            "ato_set_predictability",
            "personnel_driven_tendency_leakage",
            "tendency_disguise_capacity",
        ],
    },
    {
        "slug": "transition_trigger_predictability",
        "title": "Transition-Trigger Predictability",
        "summary": (
            "Captures how reliably a team initiates fast-break offense from a "
            "narrow set of identifiable triggers — made free throws, defensive "
            "rebounds from the center, specific guard-led outlets — "
            "enabling the opponent to pre-set transition defense for the known source."
        ),
        "stat_signature": (
            "Transition share of total possessions above 20% combined with trigger "
            "concentration above 60% from one rebound source signals a scoutable "
            "pattern; outlet target entropy below 1.2 bits on defensive rebound "
            "possessions identifies a telegraphed push pattern."
        ),
        "mechanism": (
            "Opponents who identify the primary transition trigger — typically a "
            "specific guard outlet or a rim-runner lane — can sprint back to "
            "deny the preferred lane before the ball reaches the outlet, "
            "forcing the offense into a slower secondary break rather than a "
            "two-on-one advantage."
        ),
        "conditions": (
            "Most predictable against defenses that track rebound outlet tendencies "
            "and can communicate the trigger identification in real time; "
            "less predictable in free-form transition systems where the push "
            "decision is based on live read rather than scripted trigger."
        ),
        "magnitude": (
            "Defenses that correctly anticipate the transition trigger deny the "
            "preferred lane on an estimated 15-25% of rebound-to-run possessions; "
            "converting those from secondary breaks to half-court sets costs "
            "approximately 0.10-0.15 points per possession."
        ),
        "links": [
            "pace_script_predictability",
            "first_option_isolation_predictability",
            "personnel_driven_tendency_leakage",
            "shot_location_entropy",
        ],
    },
    {
        "slug": "fourth_quarter_shot_distribution_narrowing",
        "title": "Fourth-Quarter Shot-Distribution Narrowing",
        "summary": (
            "Captures the measurable compression of a team's shot-type and "
            "location distribution in fourth-quarter possessions relative to the "
            "full-game baseline, reflecting the tendency to concentrate usage "
            "under late-game pressure."
        ),
        "stat_signature": (
            "Shot-type entropy drop of more than 0.4 bits from the full-game "
            "distribution to the fourth-quarter distribution is a structural narrowing; "
            "hub usage share rise above 10 percentage points in Q4 versus Q1-Q3 "
            "baseline is a common trigger; isolation share above 45% of Q4 half-court "
            "possessions identifies concentrated offenses."
        ),
        "mechanism": (
            "Coaches reduce offensive variance in high-leverage moments by running "
            "to trusted actions; the resulting shot-type concentration allows defenses "
            "to specialize coverage without sacrificing help coverage for other zones, "
            "because the complementary attack options are abandoned."
        ),
        "conditions": (
            "Narrowing is strongest in one-to-five-point games entering the fourth quarter; "
            "less pronounced in games already decided by double digits where "
            "rotation players maintain the regular-season action mix."
        ),
        "magnitude": (
            "Q4 isolation-heavy units score approximately 0.07-0.12 fewer points per "
            "possession than their Q1-Q3 baseline when the defense correctly "
            "pre-loads the concentrated action; the difference compounds on "
            "high-frequency Q4 possessions (eight to twelve per regulation game)."
        ),
        "links": [
            "late_clock_action_repetition",
            "shot_location_entropy",
            "first_option_isolation_predictability",
            "hot_hand_feeding_predictability",
        ],
    },
    {
        "slug": "hot_hand_feeding_predictability",
        "title": "Hot-Hand Feeding Predictability",
        "summary": (
            "Captures the degree to which a team systematically routes possessions "
            "to a recently hot shooter or scorer, creating a detectable routing "
            "bias that defenses can exploit by pre-loading coverage toward the "
            "expected recipient."
        ),
        "stat_signature": (
            "Usage share increase above 8 percentage points for a player following "
            "two or more consecutive makes signals a measurable hot-hand routing "
            "bias; the autocorrelation of possession-level routing to the same "
            "player on successive possessions above 0.25 identifies the tendency."
        ),
        "mechanism": (
            "Coaches and initiators respond to streak shooting by increasing "
            "the hot player's touch frequency; defenses that track the streak "
            "in real time can call a coverage adjustment — hard denial or additional "
            "attention — to target the anticipated feed, reducing the hot player's "
            "catch quality and disrupting the streak amplification."
        ),
        "conditions": (
            "Most exploitable when the hot player's action type is also predictable "
            "(spot-up catch-and-shoot); less exploitable when the hot player "
            "creates off the dribble and the coverage commitment risks freeing "
            "other attackers on drive-and-kick."
        ),
        "magnitude": (
            "Pre-loaded denial of the hot-hand feed reduces catch quality to the "
            "level of non-hot possessions, eliminating the estimated 0.08-0.14 "
            "points-per-possession premium associated with hot-player touches "
            "when coverage is neutral."
        ),
        "links": [
            "fourth_quarter_shot_distribution_narrowing",
            "first_option_isolation_predictability",
            "tendency_disguise_capacity",
            "shot_location_entropy",
        ],
    },
    {
        "slug": "defensive_coverage_predictability",
        "title": "Defensive Coverage Scheme Predictability",
        "summary": (
            "Captures how reliably a defense telegraphs its ball-screen coverage "
            "choice — whether the big drops into a zone or the defense switches — "
            "before the offensive action fully develops, phrased without invoking "
            "matchup terminology."
        ),
        "stat_signature": (
            "Coverage-type entropy across ball-screen situations below 1.2 bits "
            "indicates a high-predictability defense; single-coverage-type deployment "
            "above 75% of ball-screen possessions is a measurable signal; "
            "big-man positioning at ball-screen initiation predicts the coverage "
            "choice with above 70% accuracy from film charting."
        ),
        "mechanism": (
            "Defensive coordinators select a dominant coverage philosophy to maximize "
            "execution consistency; offenses that identify the commitment can script "
            "counter-reads before the possession — attacking the drop with pull-up "
            "or attacking the switch with post-up sequences — removing "
            "the read-and-react layer from the offense's decision cost."
        ),
        "conditions": (
            "Predictability costs most when the offense has scripted secondary "
            "reads for each coverage type and can execute them without needing "
            "the primary action to generate the coverage information first."
        ),
        "magnitude": (
            "Offenses that pre-read a predictable coverage score approximately "
            "0.06-0.10 more points per ball-screen possession than offenses "
            "reacting to the coverage after initiation; the effect accumulates "
            "across 20-30 ball-screen possessions per game."
        ),
        "links": [
            "pick_and_roll_tendency_telegraphing",
            "counter_action_absence",
            "zone_trigger_tendency",
            "tendency_disguise_capacity",
        ],
    },
    {
        "slug": "zone_trigger_tendency",
        "title": "Zone-Defense Trigger Tendency",
        "summary": (
            "Captures the situational conditions under which a team reliably "
            "shifts into zone coverage — typically foul trouble, fatigue, or "
            "opponent shooting slump — making the transition detectable and "
            "allowing the offense to script zone-attack sequences in advance."
        ),
        "stat_signature": (
            "Zone deployment rate above 12% overall with a foul-trouble trigger "
            "above 60% of zone possessions signals a reactive and predictable "
            "zone philosophy; zone entry rate that doubles in specific game contexts "
            "(third foul on a starter, double-digit deficit) is a chartable tell."
        ),
        "mechanism": (
            "Zone defense is deployed reactively to manage personnel or disrupt "
            "rhythm; when the trigger conditions are identifiable, offenses "
            "substitute ball-handlers with better zone-attack skills, set up "
            "pre-designed overload principles, and call timeouts to draw up "
            "zone-specific sets immediately after the trigger fires."
        ),
        "conditions": (
            "Most exploitable when the trigger is systematic and the offensive "
            "team has rehearsed zone-attack alternatives; less exploitable in "
            "packaged zone schemes that use zone proactively and "
            "unpredictably throughout the game."
        ),
        "magnitude": (
            "Offenses that correctly anticipate zone deployment score approximately "
            "0.06-0.12 more points per possession when entering the zone with a "
            "pre-set attack than when reacting to it after the coverage is shown; "
            "effect concentrates on two to four trigger possessions per game."
        ),
        "links": [
            "defensive_coverage_predictability",
            "situational_substitution_pattern",
            "counter_action_absence",
            "tendency_disguise_capacity",
        ],
    },
    {
        "slug": "side_of_floor_preference_tendency",
        "title": "Side-of-Floor Preference Tendency",
        "summary": (
            "Captures a team's tendency to initiate and finish its most frequent "
            "actions predominantly from one side of the court, creating an "
            "identifiable spatial bias that defenses can exploit with one-sided "
            "loading schemes."
        ),
        "stat_signature": (
            "Left-or-right side possession share above 58% on half-court initiations "
            "signals a directional bias; corner-three attempt asymmetry above 60-40 "
            "split between sides is a common tell; ball-screen initiation side "
            "above 65% from one half of the floor is chartable across a season."
        ),
        "mechanism": (
            "Primary handlers with a dominant driving direction and screeners "
            "who prefer one slot naturally bias the attack to a floor side; "
            "defenses that recognize the asymmetry over-rotate defenders to the "
            "preferred side and concede the weak-side floor, reducing threat "
            "coverage only in the zones the offense rarely uses."
        ),
        "conditions": (
            "Most exploitable when the preference is stable across game states; "
            "less exploitable when the side preference is a function of matchup "
            "context and the offense adapts its side preference based on "
            "which defensive personnel is stationed where."
        ),
        "magnitude": (
            "Defenses exploiting a strong side-of-floor bias can load one half "
            "of the court and reduce corner-three attempts from the preferred side "
            "by an estimated 15-25%; converting those attempts to non-preferred "
            "side or contested shots costs approximately 0.04-0.08 points per attempt."
        ),
        "links": [
            "shot_location_entropy",
            "pick_and_roll_tendency_telegraphing",
            "counter_action_absence",
            "defensive_coverage_predictability",
        ],
    },
    {
        "slug": "counter_action_absence",
        "title": "Counter-Action Absence",
        "summary": (
            "Captures whether an offense lacks a credible secondary action that "
            "punishes a defense for over-committing to stop the primary tendency, "
            "measuring how fully the offense's threat space collapses when the "
            "primary action is taken away."
        ),
        "stat_signature": (
            "Offensive efficiency drop of more than 0.12 points per possession "
            "when the primary action is forced into a secondary read signals "
            "weak counter-action depth; transition to secondary actions occurring "
            "on only 15% of possessions when the primary is shut indicates "
            "limited counter-action scripting."
        ),
        "mechanism": (
            "An offense with a credible counter forces defensive coverage to "
            "remain honest; when no effective counter exists, defenses can "
            "over-commit personnel and help to the primary action without "
            "conceding meaningful secondary scoring, eliminating the read-and-react "
            "cost the offense intended to impose."
        ),
        "conditions": (
            "Counter-action absence is most damaging against prepared defenses "
            "in late-series or late-game contexts where the primary tendency "
            "is already fully scouted; less damaging against unprepared opponents "
            "who do not commit enough resources to force the secondary read."
        ),
        "magnitude": (
            "Offenses without a credible counter see their primary-action frequency "
            "shut down by 30-40% under aggressive scheme commitment, "
            "and their secondary-action efficiency is only 0.75-0.85 points "
            "per possession — a degradation of 0.15-0.25 from primary-action baselines."
        ),
        "links": [
            "first_option_isolation_predictability",
            "pick_and_roll_tendency_telegraphing",
            "tendency_disguise_capacity",
            "shot_location_entropy",
        ],
    },
    {
        "slug": "tendency_disguise_capacity",
        "title": "Tendency-Disguise Capacity",
        "summary": (
            "Measures an offense's ability to mask its preferred actions through "
            "motion, misdirection, and formation variation, maintaining "
            "effective entropy in play-call execution even when the underlying "
            "tendency preference is strong."
        ),
        "stat_signature": (
            "Ratio of observed action-type entropy to preferred-action frequency "
            "above 1.6 indicates high disguise capacity; formation variation "
            "per preferred action above three distinct setups signals deception "
            "depth; lead-up motion length before primary action initiation "
            "above 4.5 seconds per possession is associated with higher entropy."
        ),
        "mechanism": (
            "Pre-action motion sequences, false-action reads, and multiple "
            "valid entry points for the same play confuse the defense's ability "
            "to distinguish the primary action from its alternatives until "
            "the coverage commitment point has passed; the information "
            "advantage is preserved even when the destination is predictable."
        ),
        "conditions": (
            "Disguise capacity is most valuable when the offense has a strong "
            "primary tendency that would otherwise be over-defended; "
            "less necessary in offenses with genuine action diversity "
            "where disguise is redundant."
        ),
        "magnitude": (
            "Offenses that disguise a concentrated tendency score approximately "
            "0.08-0.14 more points per possession on the primary action "
            "compared to offenses with the same tendency concentration but "
            "no disguise motion, capturing the full efficiency of the preferred play."
        ),
        "links": [
            "play_call_entropy_after_timeout",
            "first_option_isolation_predictability",
            "counter_action_absence",
            "ato_set_predictability",
        ],
    },
    {
        "slug": "pace_script_predictability",
        "title": "Pace-Script Predictability",
        "summary": (
            "Captures whether a team's intended pace of play — fast-break "
            "frequency, average seconds per possession, and half-court "
            "clock-use targets — follows a recognizable game-script that "
            "opponents can prepare for and counter through possession-length manipulation."
        ),
        "stat_signature": (
            "Standard deviation of average seconds-per-possession across games "
            "below 2.5 seconds signals a rigid pace script; fast-break "
            "initiation rate stable within 3 percentage points across ten-game "
            "rolling windows indicates a fixed tempo target; "
            "shot-clock usage share in the under-eight-second window "
            "above 30% is a pace-script characteristic."
        ),
        "mechanism": (
            "Teams that play to a specific pace preference become vulnerable "
            "to pace manipulation; a slower-tempo opponent that extends "
            "possessions through legal delays or intentional fouls "
            "forces a fast-pace team into fewer possessions and more "
            "half-court sets, degrading their structural efficiency advantage."
        ),
        "conditions": (
            "Pace-script rigidity hurts most against opponents with extreme "
            "opposite tempo preferences who can pull the pace to "
            "an uncomfortable midpoint; less harmful against pace-neutral "
            "opponents who do not actively manipulate possession length."
        ),
        "magnitude": (
            "Fast-pace teams forced into slow-pace games (below 92 possessions "
            "from a typical 100-plus target) lose an estimated 2-4 points "
            "per game from the tempo degradation; the effect is larger "
            "when the team lacks a half-court execution identity to substitute."
        ),
        "links": [
            "transition_trigger_predictability",
            "late_clock_action_repetition",
            "play_call_entropy_after_timeout",
            "shot_location_entropy",
        ],
    },
]
