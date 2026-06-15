"""scripts.platformkit.specs.predictabilitytendencies_mlb — MLB PredictabilityTendencies concept nodes.

Person-free, market-honest intelligence spec for the brain rebuild pipeline.
All fields are descriptive calibration intelligence; no edge or ROI is claimed.
"""
from __future__ import annotations

SPORT: str = "MLB"
FAMILY: str = "PredictabilityTendencies"

CONCEPTS: list[dict] = [
    {
        "slug": "first_pitch_fastball_predictability",
        "title": "First-Pitch Fastball Predictability",
        "summary": (
            "Pitchers who throw fastballs on the first pitch at rates above 65% become "
            "pattern-exploitable: hitters who recognize the tendency can sit on a specific "
            "pitch type and location before any sequence information has been revealed."
        ),
        "stat_signature": (
            "First-pitch fastball% (FF+SI on pitch 1 of PA; >65% predictable tier, "
            "<50% low-tell tier); first-pitch swing rate against (elevated when hitters "
            "anticipate; 38%+ suggests tendency is widely scouted)."
        ),
        "mechanism": (
            "Count leverage is highest before any pitch: a hitter who correctly predicts "
            "pitch type on pitch 1 can square up a hittable offering with no two-strike "
            "penalty for a wrong read. Fastball-first tendencies that are count- and "
            "batter-agnostic are the most exploitable because they require no opponent-specific "
            "scouting — the pattern is self-revealing across a small sample of PAs."
        ),
        "conditions": (
            "Most exploitable against patient lineups that track pitch type from release "
            "point early in the game; tendency is suppressed when a pitcher varies first-pitch "
            "breaking-ball usage above 25% or when catcher signs rotate meaningfully. "
            "Amplified in favorable hitting counts where the batter is already hunting."
        ),
        "magnitude": (
            "Hitters who correctly anticipate first-pitch fastball post xwOBA on those "
            "pitches roughly 60-80 points above their season baseline, reflecting both "
            "the advantageous contact angle and zero surprise-cost of the offering."
        ),
        "links": [
            "count_based_pitch_mix_entropy",
            "two_strike_putaway_pitch_tipping",
            "pitch_tipping_mechanical_leakage",
            "sequencing_repetition_by_inning",
        ],
    },
    {
        "slug": "two_strike_putaway_pitch_tipping",
        "title": "Two-Strike Putaway-Pitch Tipping",
        "summary": (
            "Pitchers who default to a single off-speed or breaking pitch in two-strike "
            "counts with high frequency telegraph their putaway intent; hitters who recognize "
            "the tendency can commit earlier, raising contact quality on the most dangerous "
            "pitches in the arsenal."
        ),
        "stat_signature": (
            "Two-strike breaking-ball or changeup usage% (>55% to one pitch type signals "
            "predictability); swing rate on two-strike off-speed (elevated if scouted); "
            "whiff rate decline across season on two-strike putaway pitch (early-to-late)."
        ),
        "mechanism": (
            "Two-strike counts force the pitcher to deploy their best swing-and-miss pitch, "
            "but when hitters learn which pitch that will be, the element of surprise — "
            "which accounts for a significant share of swing-and-miss generation — is lost. "
            "The hitter narrows their swing decision window to the anticipated pitch and "
            "location, converting a dominant count advantage into a contestable pitch."
        ),
        "conditions": (
            "Tendency is strongest against opposing pitchers who have faced a given lineup "
            "multiple times in the same season; scouted more thoroughly in the second half "
            "when data on two-strike sequencing has accumulated. High-fastball-velocity arms "
            "that rely on secondary offerings for putaway are most exposed."
        ),
        "magnitude": (
            "When two-strike putaway pitch whiff rate declines more than 8 percentage points "
            "from first-to-third time through the order, the pattern-exposure effect on "
            "xSLG for those contact events is typically 50-70 points above baseline."
        ),
        "links": [
            "first_pitch_fastball_predictability",
            "count_based_pitch_mix_entropy",
            "third_time_through_pattern_exposure",
            "location_pattern_predictability",
        ],
    },
    {
        "slug": "count_based_pitch_mix_entropy",
        "title": "Count-Based Pitch-Mix Entropy",
        "summary": (
            "A pitcher's decision entropy across counts — how uniformly pitch types are "
            "distributed — determines how much information a hitter can extract from count "
            "alone; low-entropy count profiles (one pitch type >60% in specific counts) "
            "are the most mechanically exploitable sequencing patterns in the arsenal."
        ),
        "stat_signature": (
            "Shannon entropy of pitch-type distribution by count bucket (0-0, ahead, behind, "
            "two-strike); minimum entropy count (lowest information value to hitter); "
            "pitch-mix Gini coefficient per count (>0.55 signals one-pitch-dominant counts)."
        ),
        "mechanism": (
            "Information theory applied to pitch sequencing shows that predictability "
            "scales with the inverse of decision entropy: a pitcher who throws 65% curveballs "
            "in 0-2 counts gifts the hitter a significant prior that reduces the cognitive "
            "cost of the swing decision. Lower entropy in any single count bucket is "
            "effectively a free scouting report delivered mid-plate-appearance."
        ),
        "conditions": (
            "Most impactful facing analytically prepared lineups that track count-based "
            "usage splits within a game; amplified when pitchers are working behind in counts "
            "more than usual, forcing retreat to highest-confidence pitch types. "
            "Effect compounds across a three-game series as the data sample accumulates."
        ),
        "magnitude": (
            "The xwOBA gap between PAs where the hitter's pre-pitch fastball expectation "
            "is above 70% versus below 40% (as inferred from count and pitcher tendency) "
            "is roughly 35-55 points, driven by improved timing and swing path optimization."
        ),
        "links": [
            "first_pitch_fastball_predictability",
            "two_strike_putaway_pitch_tipping",
            "sequencing_repetition_by_inning",
            "leverage_driven_pitch_narrowing",
        ],
    },
    {
        "slug": "sequencing_repetition_by_inning",
        "title": "Sequencing Repetition by Inning",
        "summary": (
            "Pitchers who recycle nearly identical pitch sequences across plate appearances "
            "within the same inning become pattern-readable by the second and third hitters "
            "who observed earlier at-bats; within-inning sequence repetition is one of the "
            "fastest-decaying forms of information advantage for the pitcher."
        ),
        "stat_signature": (
            "Sequence-repetition index: % of PAs in an inning sharing pitch-type order with "
            "the first PA of that inning (>45% flags high repetition); variation in "
            "pitch-3 selection conditional on pitches 1-2 being identical across PAs."
        ),
        "mechanism": (
            "Each PA in an inning where a pitcher uses the same 2-pitch setup reveals "
            "the sequence to the on-deck hitter, who can plan around the setup. Unlike "
            "game-to-game pattern learning, within-inning pattern recognition requires "
            "almost no prior scouting — live observation within the same game suffices. "
            "Pitchers who mix openings more aggressively between PAs deny this real-time edge."
        ),
        "conditions": (
            "Amplified in innings where the pitcher faces the top of the order a second "
            "time, against lineups with veterans who communicate actively in the dugout, "
            "and in hitter-friendly parks where sequence exploitation has higher run-value "
            "because extra-base power is available on well-anticipated pitches."
        ),
        "magnitude": (
            "Hitters later in an inning after observing one or more same-sequenced PAs "
            "show roughly a 6-10% increase in contact rate and a 40-50 point xwOBA lift "
            "on the anticipated pitch type relative to first-PA baseline within the inning."
        ),
        "links": [
            "count_based_pitch_mix_entropy",
            "third_time_through_pattern_exposure",
            "first_pitch_fastball_predictability",
            "catcher_pattern_predictability",
        ],
    },
    {
        "slug": "pitch_tipping_mechanical_leakage",
        "title": "Pitch-Tipping Mechanical Leakage",
        "summary": (
            "Pre-delivery mechanical tells — grip adjustment timing, glove position, "
            "arm slot micro-variation, or head position changes — that correlate with "
            "pitch type enable hitters and baserunners to identify the offering before "
            "release, collapsing the deception window entirely."
        ),
        "stat_signature": (
            "Release-point cluster separation by pitch type (elite pitchers maintain "
            "<2 inch spread; tipping arms show >4 inch separation on tunnel-relevant "
            "axis); xwOBA differential between same pitch type when cluster-separated "
            "versus when tightly grouped (tight clustering benchmarks lower damage)."
        ),
        "mechanism": (
            "The deception value of a secondary pitch depends on the hitter committing "
            "to a fastball read before the trajectory diverges; if release-point or "
            "pre-motion cues reveal pitch type, the hitter gains an extra 5-15 milliseconds "
            "of decision time — enough to optimize swing path and timing for the incoming "
            "pitch class rather than reacting to late movement."
        ),
        "conditions": (
            "Most damaging for breaking-ball pitchers whose wrist supination or grip "
            "adjustment is visible from the third-base dugout angle; historically "
            "identified through opposing coaching staff observation over multiple starts. "
            "High-strikeout pitchers who rely on tunnel effects are most vulnerable if "
            "the effect is disrupted by a mechanical tell."
        ),
        "magnitude": (
            "When a tip is actively exploited, xwOBA on the tipped pitch type rises "
            "roughly 80-120 points above the untipped baseline for that pitcher in "
            "that stretch, representing near-complete collapse of secondary pitch value."
        ),
        "links": [
            "first_pitch_fastball_predictability",
            "two_strike_putaway_pitch_tipping",
            "count_based_pitch_mix_entropy",
            "pitch_clock_rhythm_tell",
        ],
    },
    {
        "slug": "location_pattern_predictability",
        "title": "Location-Pattern Predictability",
        "summary": (
            "Pitchers who return to identical horizontal or vertical zones within a "
            "count or batter-handedness context create exploitable location clustering "
            "that hitters can anticipate; elite sequencing diversifies location alongside "
            "pitch type so neither dimension becomes a reliable pre-pitch prior."
        ),
        "stat_signature": (
            "Location entropy by zone-bucket per count (heart, shadow, chase, waste); "
            "repeat-zone rate on consecutive pitches to the same batter (>40% signals "
            "location lock); arm-side versus glove-side split of putaway pitch placement."
        ),
        "mechanism": (
            "A hitter who has seen two consecutive pitches in the lower glove-side shadow "
            "has implicit Bayesian evidence that the next offering will be in a similar "
            "zone; even if pitch type varies, zone-clustering allows the hitter to "
            "pre-weight their swing path, recovering some of the deception cost of "
            "pitch-type diversity. Location and type must both vary to maximize unpredictability."
        ),
        "conditions": (
            "Strongest effect for sinker-heavy pitchers who work low-and-arm-side "
            "predominantly against same-hand hitters; tends to self-correct when a "
            "hitter squares one pitch and forces the pitcher to adjust. "
            "Against pull-heavy lineups, location clustering on the inner half is "
            "especially costly because it aligns with the hitter's natural strength zone."
        ),
        "magnitude": (
            "Location clustering indexes correlate with BABIP elevation of 15-25 points "
            "above pitcher norms; when combined with pitch-type predictability, the "
            "combined effect on hard-contact rate (xEV >95 mph) is roughly 4-7% higher."
        ),
        "links": [
            "count_based_pitch_mix_entropy",
            "two_strike_putaway_pitch_tipping",
            "sequencing_repetition_by_inning",
            "catcher_pattern_predictability",
        ],
    },
    {
        "slug": "fastball_usage_narrowing_under_fatigue",
        "title": "Fastball-Usage Narrowing Under Fatigue",
        "summary": (
            "As pitch counts rise and arm fatigue accumulates, pitchers progressively "
            "retreat to their primary fastball at the expense of secondary mix, converting "
            "a varied early-game profile into a predictably fastball-heavy late-game one "
            "that hitters can exploit with narrower anticipatory windows."
        ),
        "stat_signature": (
            "Fastball% by pitch-count bucket (<50, 50-75, 75-100, >100); secondary "
            "usage rate decline from innings 1-3 to innings 6-7+ (>8% decline signals "
            "predictable narrowing); swinging-strike rate on fastball by pitch-count bucket "
            "(decline confirms hitters are adjusting to fastball anticipation)."
        ),
        "mechanism": (
            "Fatigue reduces confidence in secondary command: sliders that were sharp at "
            "60 pitches lose break consistency at 90, and pitchers who throw a flat slider "
            "against a good hitter risk hard contact more than a well-located fastball. "
            "The result is a rational but predictable retreat to the primary pitch, "
            "a pattern alert hitters begin tracking from the first few innings."
        ),
        "conditions": (
            "Amplified for pitchers with a large velocity gap between their primary and "
            "secondary offerings (hitters who can eliminate off-speed are dangerous); "
            "most impactful facing a lineup's third or fourth time through the order "
            "when batter adjustment and pitch-count exposure coincide."
        ),
        "magnitude": (
            "Fastball xwOBA in pitch-count buckets above 80 rises roughly 30-50 points "
            "above pre-fatigue levels for pitchers who narrow significantly; the effect "
            "is largest for starters who transition from multi-pitch profiles to "
            "fastball-dominant one-pitch approaches above 90 pitches."
        ),
        "links": [
            "third_time_through_pattern_exposure",
            "count_based_pitch_mix_entropy",
            "leverage_driven_pitch_narrowing",
            "first_pitch_fastball_predictability",
        ],
    },
    {
        "slug": "breaking_ball_in_dirt_tendency",
        "title": "Breaking-Ball-in-the-Dirt Tendency",
        "summary": (
            "Pitchers who habitually bury breaking balls in the dirt on two-strike counts "
            "develop a readable tell for baserunners who time the ball-in-dirt trigger; "
            "the combination of hitter strikeout vulnerability and base-theft opportunity "
            "creates a dual-risk pattern from a single pitch-selection tendency."
        ),
        "stat_signature": (
            "Dirt-ball% on two-strike breaking pitches (>18% elevated; <10% controlled); "
            "passed-ball and wild-pitch rate on breaking balls by count; stolen-base "
            "attempt rate on two-strike breaking-ball-heavy pitchers (above-baseline signals "
            "baserunner exploitation)."
        ),
        "mechanism": (
            "Intentional dirt breaking balls generate high swing-and-miss rates but also "
            "signal a readable cue to runners: a sharp downward trajectory off the plate "
            "can be identified early enough to trigger a steal attempt before the receiver "
            "recovers. Pitchers who cannot vary the depth of their chase pitch — keeping "
            "some near the zone rather than buried — become predictable to both hitter "
            "and baserunner simultaneously."
        ),
        "conditions": (
            "Most impactful with a fast runner on first in two-strike counts where the "
            "batter is likely to expand, giving the runner a green light on the first "
            "breaking ball read. Amplified when the receiver has below-average blocking "
            "metrics, making the dirt ball more likely to escape and advance runners freely."
        ),
        "magnitude": (
            "Stolen-base success rates against pitchers with high dirt-ball tendencies on "
            "two-strike breaking balls run roughly 78-85% versus the league baseline of "
            "72-76%, reflecting the anticipatory advantage of the pre-read trigger."
        ),
        "links": [
            "two_strike_putaway_pitch_tipping",
            "base_stealing_trigger_predictability",
            "catcher_pattern_predictability",
            "count_based_pitch_mix_entropy",
        ],
    },
    {
        "slug": "hitter_swing_decision_predictability",
        "title": "Hitter Swing-Decision Predictability",
        "summary": (
            "Hitters who exhibit highly stable and exploitable swing-or-take patterns "
            "— particularly elevated chase rates on specific pitch types or zones — "
            "allow pitchers to concentrate their attack on a narrow band of offerings "
            "with predictable hitter responses, reducing the pitcher's decision risk."
        ),
        "stat_signature": (
            "O-Swing% on specific pitch types (breaking ball chase >38% flags "
            "high predictability); take rate on first-pitch fastball heart zone "
            "(<40% swing signals aggressive exploitability); swing-decision entropy "
            "across pitch types (low entropy = one dimension of hitter tendency dominates)."
        ),
        "mechanism": (
            "When a hitter's chase tendency on a specific pitch type is consistent "
            "across counts and game states, the pitcher can treat that pitch as a "
            "reliable out-getter in high-leverage moments without sequence setup, "
            "effectively bypassing the need for elaborate deception. The predictability "
            "reversal — hitter being the predictable party — shifts decision leverage "
            "to the pitcher who controls pitch selection."
        ),
        "conditions": (
            "Most exploitable by pitchers whose primary pitch matches the hitter's "
            "highest-chase bucket; tendency is most durable for older hitters whose "
            "chase patterns have calcified, and for hitters whose swing mechanics "
            "structurally pull them toward a specific quadrant of the zone."
        ),
        "magnitude": (
            "Pitchers facing hitters with O-Swing% above 38% on their primary secondary "
            "offering post whiff rates 10-15 percentage points above their season average, "
            "reflecting the compounding of repertoire strength and hitter tendency alignment."
        ),
        "links": [
            "count_based_pitch_mix_entropy",
            "platoon_driven_pitch_mix_tells",
            "two_strike_putaway_pitch_tipping",
            "location_pattern_predictability",
        ],
    },
    {
        "slug": "platoon_driven_pitch_mix_tells",
        "title": "Platoon-Driven Pitch-Mix Tells",
        "summary": (
            "Pitchers who dramatically alter pitch-mix by batter handedness create "
            "legible patterns for switch-hitter deployment and pinch-hit decisions; "
            "platoon-specific repertoire narrowing is one of the most documented "
            "forms of sequencing predictability at the team-strategy level."
        ),
        "stat_signature": (
            "Fastball-versus-breaking-ball mix differential by batter hand (>20% gap "
            "between same-hand and opposite-hand profiles signals strong platoon tell); "
            "changeup usage% against opposite-hand batters (high usage narrows the "
            "anticipated secondary pitch to one type)."
        ),
        "mechanism": (
            "Pitchers who rely on arm-side breaking balls heavily against same-hand hitters "
            "telegraph their intended weapon when the batter's handedness is known; the "
            "opposing manager can exploit this by stacking same-hand hitters or bringing "
            "a specific-handedness pinch hitter to counter a platoon-dependent reliever. "
            "The tell is systemic rather than in-game and is discoverable from public data."
        ),
        "conditions": (
            "Most impactful in late-game situations where the opposing manager has "
            "platoon flexibility; amplified for single-pitch relievers whose entire "
            "identity is one pitch to one handedness, making the pitch-mix trivially "
            "predictable regardless of count or game state."
        ),
        "magnitude": (
            "The platoon split (OPS same-hand versus opposite-hand) for pitchers "
            "with high mix-differential profiles averages 60-90 points wider than "
            "for pitchers with balanced platoon profiles, driven largely by the "
            "anticipatory advantage the aligned batter gains from repertoire narrowing."
        ),
        "links": [
            "hitter_swing_decision_predictability",
            "count_based_pitch_mix_entropy",
            "leverage_driven_pitch_narrowing",
            "first_pitch_fastball_predictability",
        ],
    },
    {
        "slug": "situational_bunt_predictability",
        "title": "Situational Bunt Predictability",
        "summary": (
            "Offensive teams whose bunt deployment correlates too cleanly with "
            "specific game states — runner on first, no outs, pitcher spot in lineup — "
            "allow the defense to pre-rotate and eliminate the bunt's run-value "
            "advantage before the pitch is thrown."
        ),
        "stat_signature": (
            "Bunt attempt rate by game state (runner-on-first/no-out rate >55% signals "
            "high predictability); sacrifice success rate for predictable-profile teams "
            "versus lower-tell teams (success rate gap of 8-12% observed across profiles); "
            "corner infield charge frequency when bunt is anticipated."
        ),
        "mechanism": (
            "Defenses that anticipate a bunt can charge corners pre-pitch and shade "
            "to ball-side coverage before the fielder even moves; the early pre-pitch "
            "rotation eliminates the bunt's primary advantage — catching the defense "
            "flat-footed and stationary. Teams with predictable bunt profiles donate "
            "the sacrifice's execution edge before it begins."
        ),
        "conditions": (
            "Amplified with a pitcher at the plate or a contact-weak hitter in a "
            "no-out / runner-on-first state where the bunt is the default play; "
            "effect is stronger against analytically prepared defenses who track "
            "bunt tendency in pre-game preparation. Artificial-turf fields with faster "
            "groundball speeds also reduce bunt success rates for anticipated attempts."
        ),
        "magnitude": (
            "Predictable-bunt teams see sacrifice success rates roughly 8-12 percentage "
            "points below the baseline because the anticipated defense removes the "
            "execution window that makes the bunt viable in the first place."
        ),
        "links": [
            "base_stealing_trigger_predictability",
            "lineup_protection_tendency",
            "hitter_swing_decision_predictability",
        ],
    },
    {
        "slug": "base_stealing_trigger_predictability",
        "title": "Base-Stealing Trigger Predictability",
        "summary": (
            "Baserunners who initiate steal attempts on highly correlated cues — "
            "specific pitch types, counts, or pitcher motion cues — become readable "
            "to the battery, allowing pre-pitch pitch-out deployment or altered "
            "tempo that negates the stolen-base threat before it materializes."
        ),
        "stat_signature": (
            "Steal attempt rate by count (0-0, 2-0 first pitch attempts signal "
            "high count-trigger predictability; >60% of attempts in one count bucket "
            "is elevated); pitch-out deployment rate against high-steal runners "
            "(above-baseline pitch-outs indicate the battery has identified the trigger)."
        ),
        "mechanism": (
            "Elite base-stealing run on pitch-read and pitcher timing, but runners who "
            "rely on count-based or pitch-type triggers become predictable because "
            "those cues are observable by catchers tracking historical attempt data. "
            "A runner who consistently goes on first-pitch breaking balls enables "
            "the battery to call a high fastball or pitch-out in those situations, "
            "converting a stolen-base threat into a caught-stealing opportunity."
        ),
        "conditions": (
            "Exploitable when the opposing battery has faced the runner multiple times "
            "and has tracked attempt patterns; amplified when the runner lacks a "
            "fallback second-move or delayed steal to disguise the primary trigger. "
            "Most relevant for runners in the 35-65 stolen-base per season range "
            "whose frequency creates a large data sample within one season."
        ),
        "magnitude": (
            "Runners whose trigger predictability is identified see caught-stealing "
            "rates rise roughly 6-12 percentage points above their season baseline "
            "in subsequent series against informed batteries, reflecting the pitch-out "
            "and timing adjustment the catcher applies once the pattern is mapped."
        ),
        "links": [
            "breaking_ball_in_dirt_tendency",
            "situational_bunt_predictability",
            "pickoff_tendency_telegraphing",
            "catcher_pattern_predictability",
        ],
    },
    {
        "slug": "catcher_pattern_predictability",
        "title": "Catcher Pitch-Calling Pattern Predictability",
        "summary": (
            "A receiver whose sign patterns can be decoded by runners on second base "
            "or by hitters through dugout relay systems undermines the entire pitch-type "
            "deception architecture; complex sign sequences and rapid rotation cycles "
            "are the primary countermeasure for pattern-readable catchers."
        ),
        "stat_signature": (
            "Signal-steal vulnerability index: OPS differential for teams batting with "
            "a runner on second (above +.030 versus empty bases suggests relay signal "
            "exploitation); battery complexity score (sign sequence length and rotation "
            "frequency as a proxy for pattern-resistance)."
        ),
        "mechanism": (
            "A runner on second with a clear sightline to the catcher's signs can decode "
            "the pitch type and relay it to the hitter through body language or timing cues "
            "within the PA; even partially accurate relay information collapses the pitcher's "
            "deception value. The catcher's countermeasure — extended sign sequences, "
            "pump fakes, and inning-to-inning rotation — restores pattern opacity at the "
            "cost of additional setup time."
        ),
        "conditions": (
            "Most impactful in day games with good visibility to second base, and when "
            "the opposing team has experienced baserunners with pattern-reading ability. "
            "Battery pairs who use simple one-sign systems or predictable count-based "
            "sign changes are most vulnerable across a three-game series."
        ),
        "magnitude": (
            "Historical studies of sign-stealing contexts show OPS differentials with "
            "a runner on second of .025-.060 for batteries using simple sign systems, "
            "equivalent to the on-base and slugging shift associated with a meaningful "
            "pitch-anticipation advantage in a relevant fraction of PAs."
        ),
        "links": [
            "sequencing_repetition_by_inning",
            "location_pattern_predictability",
            "base_stealing_trigger_predictability",
            "count_based_pitch_mix_entropy",
        ],
    },
    {
        "slug": "lineup_protection_tendency",
        "title": "Lineup-Protection Pitching Tendency",
        "summary": (
            "Pitchers who alter their attack strategy based on the on-deck hitter's "
            "quality — nibbling around a dangerous hitter to face a weaker on-deck batter "
            "— create a predictable pattern where the protected hitter can take pitches "
            "confidently, knowing walk probability is elevated by lineup-context decisions."
        ),
        "stat_signature": (
            "Walk rate differential for a given hitter when on-deck quality is high "
            "versus weak (>5 percentage point gap signals protection effect); "
            "IBB rate in non-extreme-leverage states when on-deck xwOBA is below .280 "
            "versus above .360; first-pitch strike rate differential by on-deck tier."
        ),
        "mechanism": (
            "When the on-deck hitter is weak, the pitcher has less incentive to challenge "
            "the current dangerous hitter and more incentive to expand the zone and invite "
            "weak contact or a walk followed by a double-play opportunity. The protected "
            "hitter who recognizes this tendency can take borderline pitches aggressively, "
            "converting pitcher caution into a walk or a hittable-count advantage."
        ),
        "conditions": (
            "Amplified when the on-deck quality differential is large (e.g., a cleanup "
            "hitter followed by a below-average hitter) and when the score context makes "
            "a run from a walk less damaging than a multi-run extra-base hit. "
            "Effect is largest in the middle of the lineup where protection dynamics are "
            "most acute and pitch-count conservation pressures are also present."
        ),
        "magnitude": (
            "Walk rates for protected dangerous hitters rise roughly 3-5 percentage points "
            "above their baseline when the on-deck hitter has below-average wRC+, "
            "translating to meaningful OBP inflation driven entirely by opposing pitcher "
            "tactical adjustment rather than hitter discipline improvement."
        ),
        "links": [
            "situational_bunt_predictability",
            "platoon_driven_pitch_mix_tells",
            "hitter_swing_decision_predictability",
            "leverage_driven_pitch_narrowing",
        ],
    },
    {
        "slug": "leverage_driven_pitch_narrowing",
        "title": "Leverage-Driven Pitch Narrowing",
        "summary": (
            "In high-leverage situations, pitchers who retreat to their single highest-confidence "
            "offering with elevated frequency reduce their arsenal's effective breadth "
            "precisely when hitters are most alert and analytically prepared, creating "
            "a paradox where caution amplifies predictability at peak importance."
        ),
        "stat_signature": (
            "Primary pitch usage% in high-leverage states (LI >1.5) versus low-leverage "
            "states (LI <0.7); secondary pitch whiff-rate decline in high-leverage states "
            "relative to low-leverage baseline (>6% decline signals under-use of secondary "
            "arsenal when it matters most)."
        ),
        "mechanism": (
            "The psychological pressure of high-leverage situations — where a single mistake "
            "can shift win probability sharply — causes pitchers to prioritize pitch-type "
            "confidence over deceptive variety, defaulting to the primary offering. "
            "Hitters who track leverage-conditioned repertoire shifts can identify when "
            "a pitcher's secondary arsenal will be withheld and prepare accordingly."
        ),
        "conditions": (
            "Strongest for pitchers with a large quality gap between their primary and "
            "secondary offerings, where the confidence differential is large enough to "
            "drive the retreat; also more pronounced for closers and setup arms who "
            "exclusively face high-leverage situations and whose one-pitch identity "
            "is already well-scouted."
        ),
        "magnitude": (
            "xwOBA on primary pitches in high-leverage states rises roughly 25-45 points "
            "above low-leverage baseline for pitchers with narrowing indexes above 15%, "
            "reflecting both hitter anticipation and the compounding effect of predictability "
            "at game moments with the highest per-event run-value weight."
        ),
        "links": [
            "count_based_pitch_mix_entropy",
            "fastball_usage_narrowing_under_fatigue",
            "two_strike_putaway_pitch_tipping",
            "platoon_driven_pitch_mix_tells",
        ],
    },
    {
        "slug": "pickoff_tendency_telegraphing",
        "title": "Pickoff Tendency Telegraphing",
        "summary": (
            "Pitchers who initiate pickoff throws on consistent count or lead-distance "
            "triggers allow baserunners to time the delivery and return to the bag "
            "comfortably, neutralizing the pickoff as a lead-management tool and "
            "permitting larger secondary leads with lower caught-stealing risk."
        ),
        "stat_signature": (
            "Pickoff attempt rate per holding opportunity by count (elevated on 1-0 "
            "or 2-0 counts signals count-triggered tendency); pickoff success rate "
            "(below 2% implies the attempts are readable and runners are adjusting); "
            "lead-distance expansion across pickoff-heavy pitchers (runners taking "
            "larger secondary leads than against pickoff-minimal pitchers)."
        ),
        "mechanism": (
            "A pickoff throw that occurs on a predictable count or after a fixed number "
            "of set-position glances gives the runner a countdown: once the expected "
            "pickoff has occurred, the runner knows the next delivery will be to the "
            "plate and can extend the primary lead without additional retreat risk. "
            "Pitchers who randomize pickoff timing and count eliminate this countability."
        ),
        "conditions": (
            "Most impactful against experienced baserunners who track pitcher habits "
            "across multiple appearances; amplified when the first-base coach "
            "actively communicates timing observations to the runner in real time. "
            "Pitchers working from the stretch with a high-effort leg kick are most "
            "vulnerable to lead exploitation once the pickoff pattern is decoded."
        ),
        "magnitude": (
            "Runners against pickoff-patterned pitchers achieve stolen-base jump "
            "distances (first-step lead advantage) approximately 0.3-0.5 feet larger "
            "than against unpredictable holders, translating to a meaningful success "
            "rate lift on steal attempts that originate from those expanded leads."
        ),
        "links": [
            "base_stealing_trigger_predictability",
            "breaking_ball_in_dirt_tendency",
            "pitch_clock_rhythm_tell",
            "situational_bunt_predictability",
        ],
    },
    {
        "slug": "pitch_clock_rhythm_tell",
        "title": "Pitch-Clock Rhythm Tell",
        "summary": (
            "Pitchers who settle into a consistent pitch-to-pitch tempo under the pitch "
            "clock create a rhythmic delivery pattern that hitters and baserunners can "
            "use as a timing anchor; deviations from established tempo — pauses before "
            "breaking balls, faster delivery before fastballs — constitute a rhythm-based "
            "pitch-type tell overlaid on the rules-driven time structure."
        ),
        "stat_signature": (
            "Time-between-pitches standard deviation by pitch type (low SD signals "
            "uniform tempo; SD difference >1.5 seconds between fastball and breaking "
            "ball delivery rhythms flags a tempo tell); baserunner jump-timing improvement "
            "against tempo-consistent deliveries versus varied-tempo deliveries."
        ),
        "mechanism": (
            "The pitch clock forces pitchers into a bounded time window but does not "
            "prescribe within-window tempo uniformity; pitchers who unconsciously vary "
            "their pace — pausing longer before a high-effort breaking ball or speeding "
            "up before a fastball — embed pitch-type information into their temporal "
            "footprint. Hitters tracking visual and rhythmic cues can assimilate this "
            "additional signal without explicit analytical identification."
        ),
        "conditions": (
            "Most exploitable by hitters with strong temporal processing and rhythm "
            "awareness; amplified in multi-game series where the hitter has multiple "
            "at-bats to calibrate the tempo-type association. Also leverageable by "
            "baserunners who key on delivery rhythm to time their first step on steal attempts."
        ),
        "magnitude": (
            "Tempo-tell pitchers who show greater than 1.5-second mean delivery time "
            "differentials by pitch type see contact-quality metrics on anticipated "
            "pitch types rise roughly 30-45 xwOBA points, driven by improved timing "
            "and reduced reaction-window cost."
        ),
        "links": [
            "pitch_tipping_mechanical_leakage",
            "first_pitch_fastball_predictability",
            "pickoff_tendency_telegraphing",
            "count_based_pitch_mix_entropy",
        ],
    },
    {
        "slug": "third_time_through_pattern_exposure",
        "title": "Third-Time-Through Pattern Exposure",
        "summary": (
            "The well-documented performance degradation pitchers experience facing a "
            "lineup for the third time in a game reflects accumulated pattern recognition: "
            "hitters integrate pitch-sequencing, location, and velocity information across "
            "prior at-bats and apply it as a durable within-game prior on subsequent PAs."
        ),
        "stat_signature": (
            "OPS and xwOBA differential: first time through lineup versus third time "
            "through lineup (typical degradation: +.060-.090 OPS for third-time batters); "
            "K% decline and BB% increase from first to third time through; velocity "
            "drop by 0.5-1.2 mph on average by the third rotation as fatigue compounds."
        ),
        "mechanism": (
            "By the third time through the order, every hitter has seen the pitcher's "
            "complete active repertoire in multiple counts and states, enabling them to "
            "build a reliable prior on pitch mix, sequencing tendencies, location clusters, "
            "and velocity band. The information advantage decays from early-PA uncertainty "
            "toward near-certainty on the pitcher's decision tree, fundamentally shifting "
            "the information asymmetry between pitcher and hitter."
        ),
        "conditions": (
            "Effect is strongest for starters who rely heavily on deception-and-mix "
            "rather than pure raw velocity; power arms who generate swing-and-miss from "
            "elite velocity maintain the effect to a lesser degree. Context-dependent "
            "on the hitter's in-game learning quality — patient lineup with strong "
            "at-bat communication amplifies the exposure above baseline."
        ),
        "magnitude": (
            "The third-time-through degradation is one of the most replicated patterns "
            "in pitcher performance analysis: a starter's run-prevention effectiveness "
            "declines by roughly 0.40-0.70 ERA-equivalent from the first to third time "
            "through, with the sharpest drop occurring at the transition from second to third."
        ),
        "links": [
            "sequencing_repetition_by_inning",
            "fastball_usage_narrowing_under_fatigue",
            "two_strike_putaway_pitch_tipping",
            "count_based_pitch_mix_entropy",
            "pitch_tipping_mechanical_leakage",
        ],
    },
]
