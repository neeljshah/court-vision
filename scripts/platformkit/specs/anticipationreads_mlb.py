"""MLB / AnticipationReads — dense, person-free concept nodes for the brain.

Covers the full anticipation-read spectrum in baseball: pitch-recognition, fielder
routing, baserunner reads, battery sequencing, and defensive pre-reads.  All concepts
are descriptive and person-free; no edge or ROI claim is made anywhere.
"""
from __future__ import annotations

SPORT = "MLB"
FAMILY = "AnticipationReads"

CONCEPTS: list[dict] = [
    {
        "slug": "pitch_recognition_window",
        "title": "Pitch-Recognition Decision Window",
        "summary": (
            "The brief interval after a pitcher's release in which a hitter must "
            "commit to swing or take. Hitters who resolve pitch identity earlier "
            "show lower chase rates and higher in-zone contact quality."
        ),
        "stat_signature": (
            "Chase rate below 25 % combined with zone-contact above 85 % defines "
            "an elite recognition window; an above-average hitter resolves identity "
            "within ~170 ms of release, versus ~200 ms for a below-average window."
        ),
        "mechanism": (
            "Early-recognition hitters extract velocity, spin-rate, and trajectory "
            "cues in the first 15–20 feet of ball flight; neural commitment is "
            "triggered before the ball crosses the midpoint, so earlier identity "
            "resolution translates directly to better swing-or-take decisions."
        ),
        "conditions": (
            "Effect is strongest against high-spin breaking balls and two-pitch "
            "tunneling sequences; attenuated against pure fastball pitchers where "
            "timing rather than shape discrimination drives the decision."
        ),
        "magnitude": (
            "A 5-percentage-point chase-rate gap between strong and weak recognition "
            "cohorts corresponds to roughly 15–20 points of wOBA difference "
            "on pitches outside the zone."
        ),
        "links": [
            "tunneling_read_break",
            "spin_axis_recognition",
            "velocity_band_timing_read",
            "count_leverage_pattern_read",
            "release_point_tell_read",
        ],
    },
    {
        "slug": "tunneling_read_break",
        "title": "Pitch-Tunneling Read-Break Point",
        "summary": (
            "Two pitches sharing an early flight path that diverges only after the "
            "hitter's commit point impose a late-disambiguation task; the smaller the "
            "post-tunnel separation at commit, the higher the induced whiff rate."
        ),
        "stat_signature": (
            "Pitch pairs with post-tunnel separation below 3 inches at the commit "
            "plane generate whiff rates 8–12 percentage points above single-pitch "
            "baselines; pairs above 6 inches revert to near-average whiff rates."
        ),
        "mechanism": (
            "Shared early trajectory causes the hitter's visual system to classify "
            "both pitches identically until late break; by the time shape diverges, "
            "motor commitment has already begun, leaving the hitter unable to abort "
            "or adjust the swing path effectively."
        ),
        "conditions": (
            "Maximized when a fastball and breaking ball share arm-slot and initial "
            "spin axis for the first 20 feet; attenuated when the pitcher's "
            "release-point or grip tell reveals the off-speed pitch early."
        ),
        "magnitude": (
            "The tightest tunneling pairs (separation below 2 inches) show swinging-"
            "strike rates near 35–40 %, roughly double the league-average for "
            "comparable pitch velocities."
        ),
        "links": [
            "pitch_recognition_window",
            "spin_axis_recognition",
            "release_point_tell_read",
            "velocity_band_timing_read",
        ],
    },
    {
        "slug": "spin_axis_recognition",
        "title": "Spin-Axis Recognition",
        "summary": (
            "A hitter's ability to read the direction of ball rotation from early "
            "visual cues to anticipate break direction; accurate reads convert "
            "breaking balls from whiff-inducers into hittable pitches."
        ),
        "stat_signature": (
            "Hitters with above-average breaking-ball contact (xBA above .220 on "
            "curves and sliders) distinguish spin axis within the first 10 feet of "
            "flight; the gap between high and low spin-read cohorts is roughly "
            "30–40 points of slgBA on breaking balls."
        ),
        "mechanism": (
            "Topspin, backspin, and side-spin produce characteristic seam-rotation "
            "patterns visible to the hitter's peripheral and foveal vision during the "
            "first half of ball flight; early axis identification lets the hitter "
            "pre-load the appropriate swing adjustment."
        ),
        "conditions": (
            "Most consequential against high-spin-rate breaking balls (above 2600 rpm) "
            "and against pitchers who vary spin axis intentionally; less separating "
            "against flat or moderate-spin offerings."
        ),
        "magnitude": (
            "Cohorts with demonstrated spin-read accuracy post 15–18 percentage-point "
            "lower whiff rates on breaking balls compared with those relying on "
            "late shape cues."
        ),
        "links": [
            "pitch_recognition_window",
            "tunneling_read_break",
            "count_leverage_pattern_read",
        ],
    },
    {
        "slug": "first_step_jump_reads",
        "title": "Outfielder First-Step Jump Reads",
        "summary": (
            "An outfielder's ability to initiate a route before the ball clears the "
            "infield by reading bat-ball contact sound, launch angle cues, and "
            "hitter body posture at contact."
        ),
        "stat_signature": (
            "Elite outfield route efficiency exceeds 95 % of optimal path on balls "
            "in the 85–95 mph exit-velocity band; first-step time under 0.30 s from "
            "contact correlates with a 6–8 percentage-point gain in catch probability "
            "on balls hit 25–40 degrees from the fielder's rest position."
        ),
        "mechanism": (
            "Contact sound frequency and bat follow-through angle provide earlier "
            "information than ball trajectory alone; fielders who integrate these "
            "pre-flight cues reduce time-to-first-step and optimize initial route "
            "direction before reliable ball tracking is possible."
        ),
        "conditions": (
            "Most impactful on balls with launch angles between 20 and 35 degrees "
            "where catch probability is uncertain; less separating on obvious fly "
            "balls above 40 degrees or grounders below 10 degrees."
        ),
        "magnitude": (
            "Good first-step readers post Defensive Runs Saved 4–6 runs per 1 000 "
            "chances above average outfielders in matching exit-velocity buckets."
        ),
        "links": [
            "fly_ball_carry_read",
            "contact_quality_off_bat_read",
            "relay_cutoff_anticipation",
            "tag_up_anticipation",
        ],
    },
    {
        "slug": "baserunner_secondary_lead_read",
        "title": "Secondary-Lead Jump Reads",
        "summary": (
            "A baserunner's anticipatory extension of the secondary lead timed to the "
            "pitcher's release and pitch type, enabling earlier breaks toward the next "
            "base on balls in play."
        ),
        "stat_signature": (
            "Runners who extend secondary leads 1.5–2.0 feet beyond a neutral "
            "secondary show advancement rates on balls in play 8–12 percentage points "
            "above those with conservative secondaries, controlling for batted-ball "
            "direction."
        ),
        "mechanism": (
            "The runner times the pitcher's delivery cadence and extends the secondary "
            "as the ball passes the plate; pitch recognition (fastball versus off-speed) "
            "calibrates extension because off-speed pitches allow more time to read "
            "the ball off the bat before returning."
        ),
        "conditions": (
            "Effect is largest with two outs when a full-secondary read is lower-risk, "
            "and against slower-working pitchers; reduced against pitchers with "
            "unpredictable timing or catchers with elite pop times."
        ),
        "magnitude": (
            "An aggressive, well-timed secondary converts to roughly one extra base "
            "per 12–15 balls in play compared with a conservative secondary in "
            "equivalent contexts."
        ),
        "links": [
            "steal_jump_pitch_read",
            "pickoff_move_anticipation",
            "double_steal_read",
            "tag_up_anticipation",
        ],
    },
    {
        "slug": "pickoff_move_anticipation",
        "title": "Pickoff-Move Anticipation",
        "summary": (
            "A baserunner's ability to distinguish a pickoff delivery from a pitch "
            "delivery through pre-pitch tells in the pitcher's footwork, hip rotation, "
            "and head position, allowing lead preservation under pickoff pressure."
        ),
        "stat_signature": (
            "Runners who successfully retain their primary lead on pickoff attempts "
            "show pickoff-survival rates above 90 %; those unable to read the tell "
            "return early and lose 6–10 inches of average lead distance per attempt."
        ),
        "mechanism": (
            "Left-handed pitchers' step-direction cues and right-handed pitchers' "
            "heel-drop timing encode the delivery type before the arm accelerates; "
            "runners who key on these cues can commit to returning only when true "
            "pickoff intent is recognized."
        ),
        "conditions": (
            "Most relevant against pitchers with historically high pickoff-attempt "
            "rates and varied timing; less separating against high-leg-kick pitchers "
            "who limit tell availability."
        ),
        "magnitude": (
            "Successfully reading and neutralizing pickoff pressure maintains an "
            "average lead 0.5–0.8 feet larger than runners who cannot, translating "
            "to roughly 3–4 percentage points of stolen-base success rate."
        ),
        "links": [
            "steal_jump_pitch_read",
            "baserunner_secondary_lead_read",
            "double_steal_read",
        ],
    },
    {
        "slug": "steal_jump_pitch_read",
        "title": "Stolen-Base Jump Pitch Reading",
        "summary": (
            "A runner optimizing stolen-base jump by reading pitch type from release "
            "cues, exploiting the additional reaction time that off-speed pitches "
            "grant before the catcher's throw."
        ),
        "stat_signature": (
            "Stolen-base success rates on recognized off-speed pitches exceed those "
            "on recognized fastballs by 6–9 percentage points for runners with "
            "sub-3.8 s home-to-second times; the gap narrows to 2–3 points for "
            "slower runners."
        ),
        "mechanism": (
            "An off-speed pitch takes 0.07–0.12 s longer to reach the plate than a "
            "fastball, giving the runner additional runway; recognizing off-speed "
            "early allows the runner to commit fully at release rather than waiting "
            "for contact confirmation."
        ),
        "conditions": (
            "Effect is conditional on the runner having a reliable pitch-read, catcher "
            "pop time above 2.0 s, and pitcher delivery time above 1.3 s; collapses "
            "when the battery counters with fastball-heavy running counts."
        ),
        "magnitude": (
            "In optimal conditions (pitch-read plus pitcher time above 1.35 s), "
            "success rates on off-speed reads approach 82–88 % versus 70–75 % "
            "on fastball attempts."
        ),
        "links": [
            "pickoff_move_anticipation",
            "baserunner_secondary_lead_read",
            "double_steal_read",
            "velocity_band_timing_read",
        ],
    },
    {
        "slug": "infield_positioning_anticipation",
        "title": "Infield Spray-Anticipation Positioning",
        "summary": (
            "Pre-pitch infield shading toward a hitter's predicted spray zone given "
            "count, pitch call, and platoon context, increasing the share of ground "
            "balls fielded within the anticipated zone."
        ),
        "stat_signature": (
            "Anticipated-zone ground-ball out rates rise 8–14 percentage points above "
            "neutral alignment when pre-pitch positioning correctly anticipates spray "
            "zone; the benefit is highest in two-strike counts where pitch location "
            "is more predictable."
        ),
        "mechanism": (
            "Count and pitch-call context narrow the hitter's likely contact zone; "
            "fielders who pre-shade reduce reaction distance and increase the "
            "probability of reaching balls hit into the anticipated quadrant."
        ),
        "conditions": (
            "Largest benefit in pitcher-favorable counts (0–2, 1–2) and against "
            "pull-heavy hitters facing inside pitching; smallest when count is even "
            "and pitch mix is unpredictable."
        ),
        "magnitude": (
            "Well-executed pre-pitch shading converts 2–4 additional outs per 100 "
            "ground balls compared with neutral positioning in matched batter-count "
            "contexts."
        ),
        "links": [
            "bunt_defense_anticipation",
            "hit_and_run_recognition",
            "catcher_sequence_anticipation",
            "count_leverage_pattern_read",
        ],
    },
    {
        "slug": "catcher_sequence_anticipation",
        "title": "Catcher Sequence Anticipation",
        "summary": (
            "A catcher's ability to call disruptive pitch sequences by anticipating "
            "hitter timing tendencies and zone expectations, producing called strikes "
            "on zone-edge pitches the hitter does not expect."
        ),
        "stat_signature": (
            "Catchers in the top quartile of called-strike rate on zone-edge pitches "
            "(above 28 %) show framing-adjusted sequences that exploit count-specific "
            "hitter takes; the called-strike gain on anticipated sequences is "
            "3–5 percentage points above random sequencing."
        ),
        "mechanism": (
            "A hitter's take probability on a given zone quadrant rises when the "
            "prior pitch established a different quadrant expectation; catchers who "
            "model this pattern call the disrupting pitch to exploit the elevated "
            "take probability."
        ),
        "conditions": (
            "Most effective against hitters with high zone-take rates (take rate "
            "above 60 % on pitches in zone) and in hitter-favorable counts when "
            "the hitter is hunting a specific pitch type."
        ),
        "magnitude": (
            "Sequence-aware catchers accumulate 4–7 additional called strikes per "
            "100 plate appearances against matching hitter profiles compared with "
            "count-neutral callers."
        ),
        "links": [
            "count_leverage_pattern_read",
            "infield_positioning_anticipation",
            "wild_pitch_block_anticipation",
            "pitch_recognition_window",
        ],
    },
    {
        "slug": "relay_cutoff_anticipation",
        "title": "Relay and Cutoff Anticipation",
        "summary": (
            "Fielders pre-positioning relay angles based on predicted runner "
            "advancement paths before the ball is fielded, reducing relay-throw time "
            "and suppressing extra bases on gap hits."
        ),
        "stat_signature": (
            "Relay attempts with pre-positioned cutoff alignment complete throws in "
            "0.3–0.5 s less than reactive alignment, translating to a 10–15 "
            "percentage-point reduction in runner advancement to the extra base "
            "on balls hit into the gap."
        ),
        "mechanism": (
            "Outfield hit trajectory, runner speed, and base configuration jointly "
            "constrain likely runner advancement paths; infielders who pre-read these "
            "constraints route themselves to the optimal relay position before the "
            "ball arrives, eliminating repositioning time."
        ),
        "conditions": (
            "Highest value on balls hit into the gaps with a runner on first base; "
            "diminished when ball trajectory is ambiguous until late or when the "
            "outfielder's fielding position is deep enough to shorten relay distance."
        ),
        "magnitude": (
            "Extra-base suppression from well-executed relay anticipation accounts "
            "for roughly 2–3 runs per 600 innings compared with reactive relay "
            "positioning in matched gap-hit contexts."
        ),
        "links": [
            "first_step_jump_reads",
            "fly_ball_carry_read",
            "tag_up_anticipation",
            "contact_quality_off_bat_read",
        ],
    },
    {
        "slug": "bunt_defense_anticipation",
        "title": "Bunt-Defense Pre-Read",
        "summary": (
            "Corners crashing pre-pitch to neutralize a sacrifice bunt by reading "
            "batter setup, game state, and historical bunt tendency before the ball "
            "is put in play."
        ),
        "stat_signature": (
            "Lead-runner force-out rates on anticipated bunts exceed 45 % for "
            "corners with pre-read crash timing versus under 30 % for corners "
            "reacting post-contact; the gain is largest when the crash begins "
            "0.2–0.3 s before bat-ball contact."
        ),
        "mechanism": (
            "A batter pivoting to bunt telegraphs intent through bat position and "
            "shoulder rotation before contact; corners who commit early reduce the "
            "fielding distance to the bunt, enabling throws to the lead base before "
            "the runner reaches safely."
        ),
        "conditions": (
            "Effective in sacrifice-bunt game states (one out or fewer, runner on "
            "first) against hitters with bunt rates above 8 % in matching contexts; "
            "counterproductive when the batter is executing a bunt-and-slash."
        ),
        "magnitude": (
            "Successful pre-read crashes convert roughly one additional lead-runner "
            "out per 8–10 correctly anticipated bunts compared with reactive "
            "corner positioning."
        ),
        "links": [
            "infield_positioning_anticipation",
            "hit_and_run_recognition",
            "double_steal_read",
        ],
    },
    {
        "slug": "velocity_band_timing_read",
        "title": "Velocity-Band Timing Anticipation",
        "summary": (
            "A hitter pre-setting swing timing to a pitcher's expected velocity band "
            "from prior at-bat sequencing, improving on-time contact rates when the "
            "velocity delivered matches the anticipated band."
        ),
        "stat_signature": (
            "On-time contact rate (defined as batted-ball exit velocity within 5 mph "
            "of max for that swing path) rises 12–18 percentage points when the "
            "delivered pitch matches the anticipated velocity band within ±2 mph "
            "versus pitches that cross a band boundary."
        ),
        "mechanism": (
            "The hitter's motor program encodes a timing reference from the pitcher's "
            "prior fastball velocity; when the subsequent pitch lands within the same "
            "band, the pre-loaded timing produces better synchronization than an "
            "adjusted late-recognition swing."
        ),
        "conditions": (
            "Strongest against pitchers who operate primarily within a single velocity "
            "band; substantially attenuated against pitchers who vary velocity by "
            "5+ mph systematically across an at-bat to disrupt timing."
        ),
        "magnitude": (
            "In-band anticipated pitches produce hard-contact rates (exit velocity "
            "above 95 mph) roughly 8 percentage points higher than cross-band "
            "pitches in matched pitch-location contexts."
        ),
        "links": [
            "pitch_recognition_window",
            "count_leverage_pattern_read",
            "tunneling_read_break",
            "steal_jump_pitch_read",
        ],
    },
    {
        "slug": "release_point_tell_read",
        "title": "Release-Point Tell Reading",
        "summary": (
            "A hitter detecting subtle arm-slot or grip-pressure tells that "
            "pre-signal pitch type, enabling anticipatory swing decisions before "
            "sufficient ball-flight information is available."
        ),
        "stat_signature": (
            "Against pitchers with identifiable tells, hitters with above-average "
            "early-swing accuracy (anticipated pitch type correct above 65 % of "
            "the time) show wOBA gains of 30–45 points on anticipated pitch types "
            "compared with their wOBA when the tell is masked."
        ),
        "mechanism": (
            "Grip, pronation angle, and arm slot at release encode the pitch type "
            "marginally before ball release; hitters who have mapped a specific "
            "pitcher's release tells can pre-commit to a pitch type, reducing "
            "the effective decision window and enabling better timing."
        ),
        "conditions": (
            "Requires prior at-bat exposure to identify a specific pitcher's tell; "
            "effect disappears when pitchers intentionally vary arm-slot or grip "
            "to eliminate the tell."
        ),
        "magnitude": (
            "When a reliable tell is present and correctly read, strikeout rate drops "
            "roughly 5 percentage points and hard-contact rate rises 6–8 percentage "
            "points on the tipped pitch type."
        ),
        "links": [
            "pitch_recognition_window",
            "tunneling_read_break",
            "spin_axis_recognition",
            "count_leverage_pattern_read",
        ],
    },
    {
        "slug": "tag_up_anticipation",
        "title": "Tag-Up Anticipation Reads",
        "summary": (
            "A baserunner reading catch certainty and outfield arm strength to time "
            "a tag-up break optimally, advancing on fly balls that would strand less "
            "anticipatory runners."
        ),
        "stat_signature": (
            "Runners who initiate tag-up breaks within 0.15 s of catch show "
            "advancement success rates 15–20 percentage points above those breaking "
            "0.3 s or later; the gap is largest on medium-depth fly balls where "
            "throw timing is decisive."
        ),
        "mechanism": (
            "The runner pre-reads outfield depth and arm rating before the pitch and "
            "positions on the base to minimize break delay at catch; earlier break "
            "narrows the throw advantage enough to convert borderline tag-up "
            "situations into safe advances."
        ),
        "conditions": (
            "Most impactful on medium-depth fly balls (250–350 feet) hit to "
            "right-center and center field where arm strength most constrains the "
            "outcome; less separating on deep flies where any runner advances "
            "comfortably."
        ),
        "magnitude": (
            "A 0.15 s advantage in break timing equates to roughly 2.5 feet of "
            "runway advantage on throws that arrive within 0.5 s of the runner."
        ),
        "links": [
            "first_step_jump_reads",
            "baserunner_secondary_lead_read",
            "relay_cutoff_anticipation",
            "fly_ball_carry_read",
        ],
    },
    {
        "slug": "count_leverage_pattern_read",
        "title": "Count-Leverage Pattern Reading",
        "summary": (
            "A hitter anticipating pitch-mix shifts by count from a pitcher's "
            "documented tendency, pre-loading swing decisions to capitalize on "
            "high-probability pitch types in hitter-favorable counts."
        ),
        "stat_signature": (
            "In 2–0 and 3–1 counts, pitchers throw four-seam fastballs at rates "
            "above 65 % league-wide; hitters who correctly anticipate and sit on "
            "the fastball in these counts produce ISO (isolated power) 80–100 "
            "points higher than in pitcher-favorable counts."
        ),
        "mechanism": (
            "Count shifts the pitcher's risk tolerance: behind in the count, "
            "pitchers favor the high-probability strike pitch; hitters who map "
            "this tendency can narrow their anticipated pitch type and pre-commit "
            "to an attack plan that rewards the most likely offering."
        ),
        "conditions": (
            "Strongest against pitchers with low pitch-mix entropy (below 1.3 bits "
            "of entropy across counts); less useful against pitchers who maintain "
            "high breaking-ball rates even in hitter-favorable counts."
        ),
        "magnitude": (
            "Hitters who demonstrate strong count-leverage recognition post slugging "
            "percentages 60–80 points above their overall slugging in 2–0 and 3–1 "
            "counts, with the gap narrowing to near zero in 0–2 counts."
        ),
        "links": [
            "pitch_recognition_window",
            "velocity_band_timing_read",
            "catcher_sequence_anticipation",
            "infield_positioning_anticipation",
            "release_point_tell_read",
        ],
    },
    {
        "slug": "wild_pitch_block_anticipation",
        "title": "Block-and-Recover Anticipation",
        "summary": (
            "A catcher pre-loading a blocking posture when pitch location and type "
            "predict a high probability of a bounced delivery, suppressing wild "
            "pitches and passed-ball runner advances."
        ),
        "stat_signature": (
            "Catchers who pre-load blocking posture on predicted dirt pitches "
            "(breaking balls in the lower third and below the zone) show "
            "block-success rates 12–18 percentage points above those reacting "
            "post-release; runner-advance suppression rises 8–10 percentage points."
        ),
        "mechanism": (
            "A catcher who reads the pitch call and location target can shift weight "
            "to the knees during the pitcher's wind-up rather than reacting to "
            "confirmed deviation; earlier weight transfer reduces the time to full "
            "blocking posture by 0.1–0.15 s, enough to intercept sharply bounced "
            "breaking balls."
        ),
        "conditions": (
            "Effective when the battery has pre-communicated the pitch call and "
            "the catcher has high confidence in the intent; attenuated on "
            "mis-executed pitches that deviate from the called location in an "
            "unexpected direction."
        ),
        "magnitude": (
            "Pre-loading reduces passed-ball and wild-pitch advance rates from "
            "roughly 55 % to below 40 % on confirmed dirt-pitch attempts in "
            "matched pitch-type and velocity contexts."
        ),
        "links": [
            "catcher_sequence_anticipation",
            "double_steal_read",
            "steal_jump_pitch_read",
        ],
    },
    {
        "slug": "double_steal_read",
        "title": "Double-Steal Anticipation",
        "summary": (
            "The battery and infield reading a first-and-third configuration to "
            "pre-anticipate a double-steal attempt, selecting a throw option that "
            "minimizes run-scoring probability."
        ),
        "stat_signature": (
            "Batteries that correctly anticipate the double-steal in first-and-third "
            "situations retire the trail runner or hold the lead runner at third "
            "above 55 % of the time; unprepared batteries concede the run-scoring "
            "advance in over 40 % of attempts."
        ),
        "mechanism": (
            "First-and-third configurations with an aggressive trail runner and a "
            "slow pitcher delivery combine to create high double-steal probability; "
            "catchers who pre-select a throw option (fake-to-third/fire-to-second "
            "or a straight-to-second read) eliminate decision latency at throw time."
        ),
        "conditions": (
            "Highest probability with one out and a left-handed hitter screening "
            "the catcher's throw line; attenuated when the trail runner's speed "
            "makes second-base theft marginal without timing help."
        ),
        "magnitude": (
            "Anticipating the double-steal correctly suppresses run-scoring "
            "probability by 12–18 percentage points compared with reactive throw "
            "selection in matched first-and-third contexts."
        ),
        "links": [
            "steal_jump_pitch_read",
            "pickoff_move_anticipation",
            "baserunner_secondary_lead_read",
            "wild_pitch_block_anticipation",
        ],
    },
    {
        "slug": "fly_ball_carry_read",
        "title": "Carry-and-Wind Anticipation Reads",
        "summary": (
            "An outfielder pre-adjusting initial depth and route direction from "
            "predicted carry given park wind conditions and exit-angle cues, "
            "improving catch probability on balls hit to the anticipated zone."
        ),
        "stat_signature": (
            "Outfielders who correctly pre-adjust for headwind carry (reducing "
            "initial depth by 5–10 feet) post catch-probability gains of 4–7 "
            "percentage points on balls in the 92–98 mph exit-velocity band; "
            "tailwind pre-adjustment yields comparable gains in the opposite "
            "direction."
        ),
        "mechanism": (
            "Wind speed and direction measurably alter ball carry at exit velocities "
            "above 88 mph; outfielders with pre-game and in-game wind awareness "
            "calibrate initial positioning and first-step direction to account for "
            "predicted carry rather than reacting to late trajectory deviation."
        ),
        "conditions": (
            "Most impactful in open-air parks with sustained winds above 10 mph; "
            "attenuated in domed environments and on calm days; also depends on "
            "consistent in-game wind that matches the pre-game read."
        ),
        "magnitude": (
            "In sustained 15+ mph headwinds, outfielders without carry adjustment "
            "over-play depth by 8–12 feet on average, reducing catch probability "
            "on warning-track fly balls by 6–10 percentage points."
        ),
        "links": [
            "first_step_jump_reads",
            "tag_up_anticipation",
            "relay_cutoff_anticipation",
            "contact_quality_off_bat_read",
        ],
    },
    {
        "slug": "contact_quality_off_bat_read",
        "title": "Off-Bat Contact-Quality Reading",
        "summary": (
            "Fielders distinguishing topspin, backspin, and slice from bat-ball "
            "contact sight and sound to anticipate ball trajectory before "
            "in-flight curvature is visible."
        ),
        "stat_signature": (
            "Fielders demonstrating high contact-quality read accuracy (correct "
            "initial move direction above 80 % of the time on topspin grounders "
            "and backspin flies) post clean-field rates 5–8 percentage points "
            "above those relying entirely on in-flight tracking."
        ),
        "mechanism": (
            "Topspin produces a characteristic lower-pitched impact sound and "
            "distinctive bat-rebound trajectory; fielders who have trained these "
            "cues can commit to the appropriate directional adjustment in the "
            "first 0.1 s after contact, before ball spin is resolved by eye."
        ),
        "conditions": (
            "Most separating on ambiguous contact types (slice line drives, "
            "sliced grounders with lateral break) where spin complicates in-flight "
            "trajectory; less separating on pure topspin grounders where trajectory "
            "is predictable early."
        ),
        "magnitude": (
            "Correct off-bat spin reads reduce reaction distance by 3–5 feet on "
            "average across all batted-ball types, equivalent to roughly 0.2 s "
            "of additional positioning time."
        ),
        "links": [
            "first_step_jump_reads",
            "fly_ball_carry_read",
            "relay_cutoff_anticipation",
        ],
    },
]
