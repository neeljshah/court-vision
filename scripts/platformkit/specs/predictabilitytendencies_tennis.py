"""Tennis PredictabilityTendencies spec — serve-pattern entropy, shot-selection tells,
and tactical telegraphing at the pattern and point-type level.

Person-free, descriptive intelligence; no edge/ROI/pick claims.
"""
from __future__ import annotations

SPORT = "Tennis"
FAMILY = "PredictabilityTendencies"

CONCEPTS: list[dict] = [
    {
        "slug": "serve_placement_predictability_on_key_points",
        "title": "Serve-Placement Narrowing on Key Points",
        "summary": (
            "Quantifies how much a server's placement distribution collapses on "
            "break points and set points relative to the overall-match baseline, "
            "concentrating on one or two zones under maximum pressure."
        ),
        "stat_signature": (
            "Serve-zone entropy (Shannon H) drops below 1.0 bit on break points "
            "for high-tendency servers (baseline H ~1.4-1.6 bits on neutral points); "
            "T-serve share on break points exceeds 55% in deuce court for a pronounced tell."
        ),
        "mechanism": (
            "Heightened cognitive load narrows shot selection toward the mentally rehearsed "
            "go-to pattern; the server sacrifices tactical variance for execution certainty, "
            "making the placement readable to opponents who have charted the match."
        ),
        "conditions": (
            "Most measurable against opponents who return aggressively from the center "
            "baseline; amplified in tiebreak situations where the cost of a double fault "
            "or weak return starts a cascading pressure loop."
        ),
        "magnitude": (
            "Return winners and redirected cross-court returns increase by roughly "
            "8-14 percentage points when the serve direction is predictable; "
            "service games on break points concede 12-18% more return-plus-one attacks."
        ),
        "links": [
            "tiebreak_serve_pattern_predictability",
            "break_point_serve_pattern_narrowing",
            "pressure_point_shot_selection_narrowing",
            "second_serve_direction_tell",
        ],
    },
    {
        "slug": "second_serve_direction_tell",
        "title": "Second-Serve Direction Tell",
        "summary": (
            "Captures systematic bias in second-serve placement — body, kick-wide, or "
            "slice-T — that diverges from the first-serve distribution in ways opponents "
            "can exploit positionally before ball contact."
        ),
        "stat_signature": (
            "Body-serve share on second delivery above 45% in the ad-court flags "
            "structural predictability; kick-wide frequency exceeding 60% in the "
            "deuce court on second serves creates a repeatable return-positioning cue."
        ),
        "mechanism": (
            "Second-serve priority shifts from placement surprise to margin safety, "
            "reinforcing the highest-margin pattern; this consistency compresses the "
            "return-position guessing window from three zones to one, enabling earlier "
            "receiver weight transfer before ball contact."
        ),
        "conditions": (
            "Most exploitable by heavy topspin returners who preload wide positioning; "
            "becomes a structural lever against opponents who have seen more than one "
            "set of data from the server's second-serve distribution."
        ),
        "magnitude": (
            "Returners who anticipate second-serve direction generate roughly 15-22% "
            "higher offensive return rates; second-serve points won drops by 5-9 "
            "percentage points when the direction tell is identified and exploited."
        ),
        "links": [
            "serve_placement_predictability_on_key_points",
            "break_point_serve_pattern_narrowing",
            "serve_plus_one_pattern_predictability",
            "tactical_disguise_capacity",
        ],
    },
    {
        "slug": "break_point_serve_pattern_narrowing",
        "title": "Break-Point Serve-Pattern Narrowing",
        "summary": (
            "Measures the reduction in first-serve directional variety specifically when "
            "facing break point, capturing how server entropy collapses most severely "
            "at the highest-stakes moment of the service game."
        ),
        "stat_signature": (
            "Directional variety index (unique zones used per 10 serves) falls from "
            "2.4-2.8 on neutral points to 1.2-1.6 on break points for tendency servers; "
            "T-serve or body-serve dominates above 65% of break-point first serves."
        ),
        "mechanism": (
            "Fear of double fault on break point suppresses adventurous placement "
            "on first serve as well, converging on the statistically safer pattern; "
            "the server's mental override of tactical planning reduces variety rather "
            "than increasing it during the most returner-favorable moment."
        ),
        "conditions": (
            "Pronounced on outdoor clay where second serves carry higher passing risk "
            "than hard courts; exacerbated for servers whose second serve lacks sufficient "
            "spin differential to produce a genuine backup option."
        ),
        "magnitude": (
            "Break-point conversion rates rise 10-18 percentage points for opponents "
            "who have identified the narrowing pattern; service game hold rate on "
            "games that include a break point drops 6-9% for high-tendency servers."
        ),
        "links": [
            "serve_placement_predictability_on_key_points",
            "second_serve_direction_tell",
            "pressure_point_shot_selection_narrowing",
            "momentum_driven_pattern_lock_in",
        ],
    },
    {
        "slug": "deuce_ad_serve_bias",
        "title": "Court-Side Serve-Direction Asymmetry",
        "summary": (
            "Captures systematic differences in preferred serve zones between the deuce "
            "and advantage courts, where a server over-indexes on one direction in one "
            "court well beyond what tactical variety prescribes."
        ),
        "stat_signature": (
            "T-serve share in deuce court exceeding 52% signals right-hand bias; "
            "wide-serve share in advantage court below 30% is atypically narrow; "
            "cross-court directional skew above 20 percentage points between courts "
            "is a mappable tendency across a full match."
        ),
        "mechanism": (
            "Dominant arm biomechanics and grip preferences make certain placement "
            "zones structurally easier to hit with consistency; servers reinforce "
            "these zones through practice and match experience, creating a charting "
            "pattern visible across opponents and tournaments."
        ),
        "conditions": (
            "Most pronounced on high-pace serves where time constraints eliminate "
            "deliberate variation; identified by opponents who chart first-serve "
            "direction per court across the first set before adjusting positioning."
        ),
        "magnitude": (
            "Returners who shift pre-return position by 20-40 cm based on court-side "
            "bias increase return-in-play rate by 7-12%; the directional read yields "
            "roughly 0.08-0.14 additional offensive returns per service game."
        ),
        "links": [
            "serve_placement_predictability_on_key_points",
            "tiebreak_serve_pattern_predictability",
            "tactical_disguise_capacity",
            "surface_driven_pattern_predictability",
        ],
    },
    {
        "slug": "first_strike_pattern_repetition",
        "title": "First-Strike Pattern Repetition Rate",
        "summary": (
            "Captures how frequently a server repeats the identical serve-plus-one "
            "combination — same placement, same response shot — within a service game "
            "or across a set, creating a telegraphed structural pattern."
        ),
        "stat_signature": (
            "First-strike pattern repetition rate above 40% (same serve zone paired "
            "with same plus-one direction) signals exploitable sequencing; elite "
            "baseline entropy sustains repetition below 28-32% across full matches."
        ),
        "mechanism": (
            "High first-strike success with a particular combination reinforces the "
            "pattern via positive feedback; the server defaults to the successful "
            "sequence under pressure, making the response shot predictable once "
            "the serve direction is read."
        ),
        "conditions": (
            "Most exploitable against aggressive returners who can take a positional "
            "read off the serve and pre-position for the plus-one; manifests most "
            "clearly on indoor hard courts where ball speed makes the read feasible."
        ),
        "magnitude": (
            "Opponents who identify a repeated first-strike sequence win the resulting "
            "rally at roughly 18-26% higher rate than the match average; disrupting "
            "the pattern by anticipating the plus-one adds 4-7 return-winner sequences "
            "per set for an aggressive returner."
        ),
        "links": [
            "serve_plus_one_pattern_predictability",
            "serve_placement_predictability_on_key_points",
            "rally_pattern_entropy",
            "tactical_disguise_capacity",
        ],
    },
    {
        "slug": "return_position_predictability",
        "title": "Return-Position Predictability",
        "summary": (
            "Captures how consistently a returner occupies the same lateral and depth "
            "position regardless of serving opponent's ball-toss location, limiting "
            "the positional adjustment that neutralizes serve variety."
        ),
        "stat_signature": (
            "Return-position lateral variance below 0.4 m across a service game "
            "indicates positional rigidity; depth variance below 0.3 m from match "
            "baseline is a structural tell for servers who exploit positioning."
        ),
        "mechanism": (
            "A fixed return position simplifies opponent serving decisions by removing "
            "the court-coverage uncertainty that wide serves exploit; the server can "
            "reliably identify uncovered zones and target them without positional "
            "adjustment disguise from the returner."
        ),
        "conditions": (
            "Exploitable by high first-serve percentage servers who can afford to "
            "target predictable exposed zones; most punishing on fast indoor surfaces "
            "where lateral recovery time from a fixed position is severely limited."
        ),
        "magnitude": (
            "Servers who target predictable return positions generate 10-17% higher "
            "direct-point rates on wide serves; return-position rigidity correlates "
            "with 5-8 fewer successful return responses per set against a probing server."
        ),
        "links": [
            "serve_placement_predictability_on_key_points",
            "rally_pattern_entropy",
            "defensive_slice_tendency",
            "surface_driven_pattern_predictability",
        ],
    },
    {
        "slug": "rally_pattern_entropy",
        "title": "Rally Shot-Selection Entropy",
        "summary": (
            "Quantifies the variety in shot-type and direction selection across rally "
            "exchanges, distinguishing players who cycle through cross-court, down-the-line, "
            "and short-angle patterns from those who return to one lane repeatedly."
        ),
        "stat_signature": (
            "Rally shot entropy (H across direction/depth/spin bins) below 1.1 bits "
            "per shot signals a low-variety pattern; cross-court dominance above 68% "
            "of groundstrokes across all rally lengths is a mappable structural tendency."
        ),
        "mechanism": (
            "Higher-margin shots (heavy cross-court topspin) are preferred in long "
            "rallies for consistency reasons; this preference becomes a learnable "
            "pattern that opponents exploit by positioning toward the dominant lane "
            "and forcing the less-practiced directional option."
        ),
        "conditions": (
            "Most pronounced in extended baseline rallies on slow clay where margin "
            "considerations dominate tactical variety; reduced on fast indoor courts "
            "where aggressive line takes require higher variance to create opportunities."
        ),
        "magnitude": (
            "Opponents who shade cross-court anticipation by 25-35 cm in high-entropy "
            "rallies generate 12-18% more winners from the dominant lane; "
            "rally entropy below 1.0 bit associates with 8-14% more opponent "
            "early-ball attacks exploiting predictable direction."
        ),
        "links": [
            "first_strike_pattern_repetition",
            "downtheline_crosscourt_tendency",
            "momentum_driven_pattern_lock_in",
            "pressure_point_shot_selection_narrowing",
        ],
    },
    {
        "slug": "approach_shot_telegraphing",
        "title": "Approach-Shot Tendency Telegraphing",
        "summary": (
            "Captures systematic approach-shot direction bias — inside-out, inside-in, "
            "or push-through — that becomes readable from body rotation and grip cues "
            "before the ball is struck."
        ),
        "stat_signature": (
            "Inside-out approach share above 58% on mid-court forehand approaches "
            "is a charting-level tendency; inside-in approach rate below 18% on "
            "backhand side mid-court balls signals structural bias toward one passing "
            "lane left unguarded."
        ),
        "mechanism": (
            "Approach-shot grips and body rotation angles provide 150-250 ms of "
            "directional cue before contact; consistent bias in approach direction "
            "allows passing-shot preparation to begin before ball departure, "
            "compressing the net rusher's positional advantage."
        ),
        "conditions": (
            "Most exploitable by opponents with strong cross-court passing shots "
            "who can exploit the identified uncovered lane; amplified on clay where "
            "slower surface speed gives the passer more time to act on the read."
        ),
        "magnitude": (
            "Passers who identify approach direction bias register passing-shot "
            "success rates 14-22% above their match average; approach-shot point "
            "win rate drops 8-13 percentage points when the direction tell is established."
        ),
        "links": [
            "net_rush_trigger_predictability",
            "downtheline_crosscourt_tendency",
            "rally_pattern_entropy",
            "tactical_disguise_capacity",
        ],
    },
    {
        "slug": "drop_shot_tell",
        "title": "Drop-Shot Setup and Execution Tell",
        "summary": (
            "Captures cues — ball bounce height, body deceleration, or grip shift — "
            "that precede a drop shot and allow the opponent to begin forward movement "
            "before ball contact, neutralizing the shot's tactical purpose."
        ),
        "stat_signature": (
            "Drop-shot success rate below 52% when the preceding rally ball is above "
            "net height (a common setup cue) indicates exploitable telegraphing; "
            "opponent recovery rate on drop shots exceeding 58% signals the tell "
            "is consistently read."
        ),
        "mechanism": (
            "Drop shots executed with excessive backswing deceleration or an altered "
            "wrist angle shift weight and shoulder alignment in ways visible 200-300 ms "
            "ahead of contact; opponents who recognize the cue begin forward momentum "
            "that converts a winner-attempt into a defensive shot."
        ),
        "conditions": (
            "Most penalized against quick-footed defenders on clay who accept the "
            "sprint trade-off; reduced effectiveness against opponents positioned deep "
            "who lack the closing speed to convert the telegraphed read."
        ),
        "magnitude": (
            "A recognizable drop-shot tell reduces outright winner rate from roughly "
            "58-65% to 40-48%; when converted to defense, opponents generate "
            "offensive passing shots from the resulting short-ball at 55-65% frequency."
        ),
        "links": [
            "approach_shot_telegraphing",
            "rally_pattern_entropy",
            "tactical_disguise_capacity",
            "defensive_slice_tendency",
        ],
    },
    {
        "slug": "downtheline_crosscourt_tendency",
        "title": "Down-the-Line and Cross-Court Direction Tendency",
        "summary": (
            "Captures a player's systematic over-indexing on one lateral direction "
            "in groundstroke exchanges, revealing whether the player favors the "
            "high-margin cross-court or the aggressive down-the-line at a mappable rate."
        ),
        "stat_signature": (
            "Cross-court groundstroke share above 70% in extended rallies (5+ shots) "
            "is a structural tendency; down-the-line attempt rate below 15% on "
            "forehand attacks despite superior positioning indicates directional timidity "
            "that opponents can shade against."
        ),
        "mechanism": (
            "Cross-court shots offer more net clearance and court space, reinforcing "
            "a conservative tendency loop; over-reliance narrows the effective "
            "cone of attack, enabling opponents to shade coverage toward the dominant "
            "direction and close off the rally sooner."
        ),
        "conditions": (
            "Most exploitable on clay where rallies extend long enough to establish "
            "the pattern before execution pressure increases; reduced on grass where "
            "shorter rallies limit the sample needed for positional adjustment."
        ),
        "magnitude": (
            "Opponents who shade cross-court by 30-50 cm generate 10-16% more "
            "early exits from the rally; enforcing a down-the-line attempt reduces "
            "unforced errors by 4-8% for the shading player from improved positioning."
        ),
        "links": [
            "rally_pattern_entropy",
            "approach_shot_telegraphing",
            "pressure_point_shot_selection_narrowing",
            "momentum_driven_pattern_lock_in",
        ],
    },
    {
        "slug": "pressure_point_shot_selection_narrowing",
        "title": "Pressure-Point Shot-Selection Narrowing",
        "summary": (
            "Captures how a player's in-rally shot-type variety contracts on game "
            "points, set points, and break-point situations relative to neutral-score "
            "baselines, concentrating on the highest-margin known pattern."
        ),
        "stat_signature": (
            "Shot-type entropy (topspin, slice, flat, drop) drops by 0.3-0.6 bits "
            "on pressure points relative to neutral; rally-ending shot placement "
            "concentrates in a single zone above 60% frequency on game-critical "
            "points for high-tendency players."
        ),
        "mechanism": (
            "Outcome aversion on high-stakes points redirects attention from tactical "
            "optimization to error avoidance, favoring the statistically safest "
            "option; this predictability allows well-prepared opponents to preload "
            "the anticipated pattern, converting defense into attack."
        ),
        "conditions": (
            "Strongest after a preceding unforced error on a low-margin shot; "
            "amplified against opponents who demonstrate consistent aggressive "
            "return of that specific pattern, reinforcing the safe-choice feedback loop."
        ),
        "magnitude": (
            "Opponent winners and forced errors increase 15-24% on pressure points "
            "for high-tendency players; pressure-point win rate drops 8-14 percentage "
            "points below match average when the narrowing pattern is charted and exploited."
        ),
        "links": [
            "serve_placement_predictability_on_key_points",
            "break_point_serve_pattern_narrowing",
            "rally_pattern_entropy",
            "momentum_driven_pattern_lock_in",
        ],
    },
    {
        "slug": "serve_plus_one_pattern_predictability",
        "title": "Serve-Plus-One Pattern Predictability",
        "summary": (
            "Measures the degree to which a server's third-shot response is determined "
            "by the serve direction used, forming a serve-response pair the opponent "
            "can anticipate before the return lands."
        ),
        "stat_signature": (
            "Conditional probability of one plus-one direction given a specific serve "
            "zone exceeding 60% is a charting-level dependency; full pair repetition "
            "rate above 35% per service game constitutes a structural pattern."
        ),
        "mechanism": (
            "Serves to specific zones open predictable court geometries for the "
            "server's next shot; when servers default to the same response for each "
            "serve direction, the pairing becomes a conditional pattern opponents "
            "can pre-load from the serve read alone."
        ),
        "conditions": (
            "Exploited by returners who have processed the pattern across at least "
            "one prior set; most impactful on indoor hard courts where ball pace "
            "compresses available reaction time but the directional read compensates."
        ),
        "magnitude": (
            "Opponents who identify and shade the plus-one direction increase "
            "rally winners on the third shot by 18-26%; serve-plus-one point win rate "
            "drops 9-15 percentage points when the pattern is successfully anticipated."
        ),
        "links": [
            "first_strike_pattern_repetition",
            "serve_placement_predictability_on_key_points",
            "tactical_disguise_capacity",
            "tiebreak_serve_pattern_predictability",
        ],
    },
    {
        "slug": "tiebreak_serve_pattern_predictability",
        "title": "Tiebreak Serve-Pattern Predictability",
        "summary": (
            "Captures the degree to which a server's placement distribution in tiebreaks "
            "diverges from match-average entropy, typically concentrating on a narrower "
            "range of patterns under maximum situational pressure."
        ),
        "stat_signature": (
            "Tiebreak serve-zone entropy below 0.9 bits compared to match average "
            "of 1.4-1.6 bits indicates severe narrowing; T-serve or body dominance "
            "above 65% in tiebreak first-serve distribution is a measurable pattern."
        ),
        "mechanism": (
            "Tiebreaks compress tactical willingness to experiment, driving servers "
            "toward the highest-confidence pattern; the cumulative importance of each "
            "point activates the same narrowing feedback as break points but across "
            "an entire condensed game structure."
        ),
        "conditions": (
            "Strongest for servers who have already demonstrated break-point narrowing "
            "within the preceding sets; indoor surfaces where ball speed intensifies "
            "pressure further reduce directional variety below the set-play baseline."
        ),
        "magnitude": (
            "Returners who exploit tiebreak serve predictability increase service-game "
            "break rates by 10-16% in tiebreak sequences; tiebreak win probability "
            "shifts 6-11 percentage points for opponents who have charted and positioned "
            "for the narrowed distribution."
        ),
        "links": [
            "serve_placement_predictability_on_key_points",
            "break_point_serve_pattern_narrowing",
            "pressure_point_shot_selection_narrowing",
            "deuce_ad_serve_bias",
        ],
    },
    {
        "slug": "net_rush_trigger_predictability",
        "title": "Net-Rush Trigger Predictability",
        "summary": (
            "Captures the identifiable ball conditions — short ball depth, forehand "
            "pull, or specific rally length — that reliably trigger a net approach, "
            "allowing the opponent to prepare the passing response early."
        ),
        "stat_signature": (
            "Net approach rate given a short ball above 0.85 m behind the service "
            "line exceeds 72% for approach-heavy players, creating a conditional cue; "
            "rally-length trigger (approaches on rally shot 3-5) above 65% frequency "
            "forms a sequencing tell."
        ),
        "mechanism": (
            "High-frequency net approaches based on a consistent trigger condition "
            "allow opponents to begin weight transfer toward the anticipated passing "
            "lane before ball contact; the read compresses the approach effectiveness "
            "window from a tactical weapon to a predictable positioning event."
        ),
        "conditions": (
            "Exploited by baseline specialists who convert net-rush situations into "
            "passing practice; most consequential against heavy topspin groundstroke "
            "opponents who execute lob-pass combinations off predictable approach reads."
        ),
        "magnitude": (
            "Passing-shot success rates rise 16-24% against predictable net rushers "
            "once the trigger condition is identified; approach-shot point win rate "
            "drops from a baseline of 65-72% to 50-58% when the trigger is charted."
        ),
        "links": [
            "approach_shot_telegraphing",
            "serve_plus_one_pattern_predictability",
            "rally_pattern_entropy",
            "defensive_slice_tendency",
        ],
    },
    {
        "slug": "defensive_slice_tendency",
        "title": "Defensive-Slice Overuse Tendency",
        "summary": (
            "Captures the rate at which a player defaults to the defensive slice "
            "in moderate-pressure situations where an offensive topspin or neutral "
            "drive would be available, creating a predictable ball-flight response."
        ),
        "stat_signature": (
            "Slice groundstroke share above 35% on balls landing in the mid-court "
            "zone from a ready position signals overuse; defensive-slice frequency "
            "on balls above shoulder height below 55% use rate is a charting-level "
            "tendency that simplifies opponent footwork planning."
        ),
        "mechanism": (
            "Repeated defensive slicing delivers low-pace balls that allow opponents "
            "to wind up and apply full swing momentum; the predictable ball-flight "
            "arc and bounce height eliminate adjustment decisions for the opponent, "
            "compounding pressure on the next ball."
        ),
        "conditions": (
            "Most punishing against heavy topspin baseliners who thrive on the "
            "high-bounce setup the slice creates; amplified on clay where slower "
            "pace gives opponents time to transfer weight fully into an attack."
        ),
        "magnitude": (
            "Opponents generate offensive shots from defensive-slice responses at "
            "roughly 22-30% higher rate than from topspin exchanges; winning "
            "patterns initiated by an opponent's slice attack succeed 14-20% more "
            "than patterns from higher-pace neutral exchanges."
        ),
        "links": [
            "rally_pattern_entropy",
            "drop_shot_tell",
            "pressure_point_shot_selection_narrowing",
            "surface_driven_pattern_predictability",
        ],
    },
    {
        "slug": "momentum_driven_pattern_lock_in",
        "title": "Momentum-Driven Pattern Lock-In",
        "summary": (
            "Captures the tendency for a player to continue repeating a recently "
            "successful shot-selection pattern beyond the point where it remains "
            "tactically surprising, allowing opponents to adjust mid-set."
        ),
        "stat_signature": (
            "Pattern-repetition rate rises above 48% within a 3-5 game winning "
            "streak inside a set for high-tendency players; directional variety "
            "index (unique zones per 10 rally shots) contracts by 0.8-1.2 units "
            "during positive-momentum stretches."
        ),
        "mechanism": (
            "Successful pattern execution reinforces selection via immediate outcome "
            "feedback, suppressing exploration; the opponent receives repeated "
            "exposures to the same ball and adjusts positioning and response shot "
            "while the player continues the fixed strategy."
        ),
        "conditions": (
            "Strongest during a momentum run that has produced 3+ consecutive points "
            "with the same pattern; least punishing against opponents who lack the "
            "pattern recognition or court positioning to exploit mid-set adjustments."
        ),
        "magnitude": (
            "Opponent break-back rate rises 12-20 percentage points during games "
            "following an identified momentum pattern; the pattern-lock-in effect "
            "contributes to set-momentum reversal sequences in approximately "
            "30-40% of cases where the pattern runs longer than 5 repetitions."
        ),
        "links": [
            "rally_pattern_entropy",
            "pressure_point_shot_selection_narrowing",
            "break_point_serve_pattern_narrowing",
            "downtheline_crosscourt_tendency",
        ],
    },
    {
        "slug": "tactical_disguise_capacity",
        "title": "Tactical Disguise and Shot-Variation Capacity",
        "summary": (
            "Measures the degree to which a player maintains consistent pre-contact "
            "body mechanics across different shot directions and types, limiting "
            "the opponent's read window before ball departure."
        ),
        "stat_signature": (
            "Pre-contact body-rotation variance below 12 degrees across cross-court "
            "and down-the-line shots signals strong disguise; opponents' predictive "
            "movement initiation timing 150 ms or later post-contact indicates "
            "effective disguise at the elite level."
        ),
        "mechanism": (
            "Identical wind-up mechanics delay the opponent's directional cue until "
            "the last 80-120 ms before contact; this compressed window prevents "
            "full weight transfer toward the target zone, reducing coverage success "
            "and increasing unforced lateral errors."
        ),
        "conditions": (
            "Most valuable against quick-anticipating opponents who exploit early "
            "cues; reduces in effectiveness on slow clay surfaces where the longer "
            "rally arc provides recovery time even from correct early directional reads."
        ),
        "magnitude": (
            "Elite disguise reduces opponent correct pre-contact movement by 20-30% "
            "relative to average; winners from disguised shots land with 15-22% "
            "higher frequency than from telegraphed equivalents due to late defender "
            "weight transfer."
        ),
        "links": [
            "drop_shot_tell",
            "approach_shot_telegraphing",
            "serve_plus_one_pattern_predictability",
            "second_serve_direction_tell",
        ],
    },
    {
        "slug": "surface_driven_pattern_predictability",
        "title": "Surface-Driven Pattern Predictability",
        "summary": (
            "Captures how strongly a player's tactical repertoire narrows on a specific "
            "surface — defaulting to clay-comfortable patterns on hard courts or "
            "grass-optimized patterns on clay — in ways that reduce match-to-match "
            "variety for opponents who have charted the surface profile."
        ),
        "stat_signature": (
            "Cross-surface rally-shot entropy differential above 0.5 bits between "
            "clay and hard court indicates surface-contingent pattern narrowing; "
            "serve-direction distribution delta above 18 percentage points on the "
            "same player across surface types reflects surface-locked tendencies."
        ),
        "mechanism": (
            "Biomechanically optimized patterns for each surface become strongly "
            "entrenched; when surface conditions deviate from the player's dominant "
            "context, the established pattern continues as a default rather than "
            "adapting to the new optimal, making it predictable for opponents who "
            "have data from that surface."
        ),
        "conditions": (
            "Most exploitable in cross-surface tournaments or when an opponent has "
            "scouted the player's behavior on the specific surface type; amplified "
            "for players whose career concentration skews heavily toward one surface."
        ),
        "magnitude": (
            "On non-preferred surfaces, predictable surface-locked patterns yield "
            "10-18% lower rally win rates compared to surface-adapted tactical variety; "
            "opponents who exploit surface-driven predictability generate 6-11% more "
            "offensive shots per game on the non-dominant surface."
        ),
        "links": [
            "rally_pattern_entropy",
            "deuce_ad_serve_bias",
            "defensive_slice_tendency",
            "tactical_disguise_capacity",
        ],
    },
]
