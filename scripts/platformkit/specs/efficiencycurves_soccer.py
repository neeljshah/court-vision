"""scripts.platformkit.specs.efficiencycurves_soccer — EfficiencyCurves for Soccer.

Dense, person-free efficiency-curve intelligence for soccer: how chance volume, possession
share, pressing intensity, buildup directness, and squad load each trace a diminishing-returns
or tradeoff curve when measured against chance quality (xG/shot). No edge or market claims;
markets are efficient.
"""
from __future__ import annotations

SPORT = "Soccer"
FAMILY = "EfficiencyCurves"

CONCEPTS: list[dict] = [
    {
        "slug": "chance_volume_quality_tradeoff_curve",
        "title": "Chance-Volume-to-Quality Tradeoff Curve",
        "summary": (
            "As a side reaches for additional shot attempts per 90, average xG per shot"
            " declines because marginal attempts occupy lower-probability locations;"
            " the slope of this decline describes the tactical cost of volume over selectivity."
        ),
        "stat_signature": (
            "xG/shot drops approximately 0.008-0.014 per additional open-play shot per 90 once"
            " total attempts exceed 14; high-volume sides above 18 shots per 90 average"
            " xG/shot near 0.08-0.09 versus 0.12-0.14 for selective sides below 12 shots per 90."
        ),
        "mechanism": (
            "Selective attacks wait for central penalty-area access; each incremental shot"
            " accepted at a wider angle or greater distance adds a structurally lower-probability"
            " attempt, pulling the mean down. The curve is steepest between 12 and 16 shots per 90"
            " where the transition from set-up chances to speculative attempts is sharpest."
        ),
        "conditions": (
            "Slope is steepest against low-block defenses that force peripheral attempts;"
            " flattest in open transition-heavy matches where additional attempts arise from"
            " high-xG counter situations rather than forced speculation."
        ),
        "magnitude": (
            "A 4-shot-per-90 volume increase at the steep portion of the curve costs"
            " approximately 0.035-0.056 xG/shot, potentially reducing total xG despite"
            " the volume gain if conversion does not offset the quality loss."
        ),
        "links": [
            "xg_per_shot_volume_elasticity",
            "shot_selection_efficient_frontier",
            "long_range_shot_speculation_curve",
            "possession_share_xg_diminishing_returns",
        ],
    },
    {
        "slug": "xg_per_shot_volume_elasticity",
        "title": "xG-per-Shot Volume Elasticity",
        "summary": (
            "The elasticity of mean chance quality with respect to total chance volume quantifies"
            " how sensitively xG/shot responds to a proportional rise in attempts; inelastic"
            " sides tolerate volume growth with minimal quality loss while elastic sides suffer"
            " rapid degradation."
        ),
        "stat_signature": (
            "Elasticity coefficient approximately -0.25 to -0.40 in open play: a 10% shot-volume"
            " increase corresponds to a 2.5-4.0% xG/shot decline; elastic sides (coefficient"
            " below -0.45) show measurable total-xG loss beyond 16 shots per 90."
        ),
        "mechanism": (
            "Elasticity is determined by the breadth of a side's chance-creation menu: sides"
            " reliant on a single central combination pattern exhaust high-quality positions"
            " quickly, making each incremental attempt significantly lower quality. Sides with"
            " multiple creation routes maintain flatter elasticity curves across a wider volume range."
        ),
        "conditions": (
            "High elasticity emerges when facing packed defenses with limited half-space access;"
            " lower elasticity in open-game contexts where additional attempts arise from"
            " genuine positional superiority rather than forced speculation."
        ),
        "magnitude": (
            "A side with elasticity of -0.40 generating 2 additional shots per 90 above its"
            " baseline of 13 loses approximately 0.006 xG/shot per additional attempt, costing"
            " roughly 0.03-0.05 aggregate xG per 90 despite the volume increase."
        ),
        "links": [
            "chance_volume_quality_tradeoff_curve",
            "shot_selection_efficient_frontier",
            "territory_to_chance_quality_conversion",
            "buildup_directness_quality_tradeoff",
        ],
    },
    {
        "slug": "shot_selection_efficient_frontier",
        "title": "Shot-Selection Efficient Frontier",
        "summary": (
            "The convex boundary of achievable total-xG across the volume-quality plane"
            " describes the maximum aggregate xG a side can generate for each possible"
            " xG/shot mean; teams operating inside the frontier sacrifice total xG through"
            " suboptimal shot selection."
        ),
        "stat_signature": (
            "Frontier-efficient sides generate 1.25-1.60 total xG per 90 at 12-15 shots;"
            " inside-frontier sides with identical volumes achieve 0.90-1.10 xG per 90;"
            " the frontier shifts outward against disorganized defenses and inward against"
            " compact high-block structures."
        ),
        "mechanism": (
            "The efficient frontier is traced by sides that correctly decline low-quality"
            " peripheral attempts while accepting every high-quality central opportunity;"
            " the frontier is a revealed constraint from the defensive structure faced"
            " rather than a fixed tactical parameter."
        ),
        "conditions": (
            "Frontier estimation requires at least 10 matches to separate structural positioning"
            " from single-match context; it collapses toward a single point in ultra-defensive"
            " matches where the entire distribution of available chances is compressed."
        ),
        "magnitude": (
            "A side operating 0.15 xG/shot below the frontier at 14 shots per 90 sacrifices"
            " approximately 2.1 xG per 90 relative to the efficient boundary — equivalent to"
            " roughly 70 goals foregone across a full season from selection inefficiency alone."
        ),
        "links": [
            "chance_volume_quality_tradeoff_curve",
            "xg_per_shot_volume_elasticity",
            "long_range_shot_speculation_curve",
            "attacking_overload_marginal_chance_value",
        ],
    },
    {
        "slug": "territory_to_chance_quality_conversion",
        "title": "Territory-to-Chance-Quality Conversion Curve",
        "summary": (
            "Final-third entry volume yields progressively lower-xG chances as a settling"
            " block absorbs positional pressure; the curve measures how much each additional"
            " entry contributes to aggregate xG against an organized defensive structure."
        ),
        "stat_signature": (
            "xG per final-third entry falls from approximately 0.07-0.10 at low entry volumes"
            " (below 30 per 90) to 0.03-0.05 at high volumes (above 50 per 90) against"
            " compact defenses; entry-to-shot conversion declines from 35% to 20-25% at peak volume."
        ),
        "mechanism": (
            "Each final-third entry against a settling block re-encounters a slightly more"
            " organized defensive shape; defenders recover positions between entries, narrowing"
            " available passing lanes and shooting corridors. Entry efficiency falls because"
            " defenders accumulate positional advantage faster than the attack can recycle."
        ),
        "conditions": (
            "Diminishing returns accelerate against sides that defend in a narrow mid-block"
            " with high compactness; the curve is flatter when entries arrive via wide overloads"
            " that force the defensive shape to stretch laterally before recompressing."
        ),
        "magnitude": (
            "Generating 15 additional entries per 90 against a compact block yields only"
            " 0.45-0.75 additional xG per 90 rather than the 1.05-1.50 expected at entry"
            " rates from open contexts — a 50-70% efficiency discount from territorial volume alone."
        ),
        "links": [
            "possession_share_xg_diminishing_returns",
            "chance_volume_quality_tradeoff_curve",
            "central_versus_wide_progression_efficiency",
            "overloaded_zone_marginal_space_value",
        ],
    },
    {
        "slug": "possession_share_xg_diminishing_returns",
        "title": "Possession-Share xG Diminishing Returns",
        "summary": (
            "Additional possession share yields progressively smaller attacking xG gains against"
            " a compact low block; beyond approximately 60% possession the marginal xG return"
            " per 5-point share rise approaches zero as defensive density absorbs extra time on ball."
        ),
        "stat_signature": (
            "xG per 90 correlation with possession share r approximately 0.30-0.40 overall;"
            " above 60% possession the marginal xG slope drops to 0.05-0.10 xG per 5-point"
            " share gain; sides above 65% possession average 1.35-1.55 xG per 90 — only"
            " marginally above the 1.20-1.40 for 55-60% possession sides."
        ),
        "mechanism": (
            "High-possession buildup against a compact block cycles through safe backward passes"
            " that maintain possession without penetrating defensive lines; each additional"
            " possession percentage point above the threshold adds safe lateral or backward"
            " ball movement rather than progressive actions, producing xG-neutral volume."
        ),
        "conditions": (
            "Diminishing returns are steepest against sides defending in two organized blocks"
            " of four with a low defensive line; flattest against high-pressing opponents"
            " who concede space in behind when possession is retained through the press."
        ),
        "magnitude": (
            "Moving from 55% to 70% possession against a settled low block yields an"
            " estimated 0.10-0.20 additional xG per 90 — roughly 3.5-7 additional expected"
            " goals across a 34-match season — a modest return on substantial territorial dominance."
        ),
        "links": [
            "territory_to_chance_quality_conversion",
            "chance_volume_quality_tradeoff_curve",
            "buildup_directness_quality_tradeoff",
            "crossing_volume_efficiency_decay",
        ],
    },
    {
        "slug": "buildup_directness_quality_tradeoff",
        "title": "Buildup-Directness Quality Tradeoff",
        "summary": (
            "Direct progressive buildup reaches the final third faster but with a less-structured"
            " attacking shape, while patient possession sequences build higher-quality chances"
            " at the cost of time on ball; the tradeoff is measurable as xG/shot against"
            " passes-per-sequence and sequence-duration."
        ),
        "stat_signature": (
            "Open-play sequences below 4 passes yield xG/shot approximately 0.10-0.14;"
            " sequences of 8-plus passes yield xG/shot 0.12-0.17 in settled play;"
            " direct sequences (2-3 passes) produce 35-45% of shots but only 25-30% of xG."
        ),
        "mechanism": (
            "Patient sequences allow supporting runs to create depth and width ahead of the ball,"
            " producing central penetration opportunities; direct sequences arrive before"
            " defenders can recover but also before attacking runners have found optimal positions,"
            " reducing the probability of a central high-xG finish."
        ),
        "conditions": (
            "The quality premium for patient buildup is largest against high-block opponents"
            " who concede transition space but recover before disorganized direct plays reach"
            " the box; against low blocks, direct play loses value because the recovery advantage"
            " disappears and patience becomes necessary."
        ),
        "magnitude": (
            "A tactical shift from 3-pass-average sequences to 7-pass-average sequences"
            " raises xG/shot by approximately 0.02-0.04 but reduces shot volume by 15-25%,"
            " yielding an estimated net xG change of -0.05 to +0.10 per 90 depending on"
            " the balance point on the volume-quality curve."
        ),
        "links": [
            "chance_volume_quality_tradeoff_curve",
            "xg_per_shot_volume_elasticity",
            "tempo_pace_chance_quality_tradeoff",
            "central_versus_wide_progression_efficiency",
        ],
    },
    {
        "slug": "press_intensity_chance_concession_curve",
        "title": "Press-Intensity Chance-Concession Curve",
        "summary": (
            "Rising pressing intensity increases turnovers won in dangerous areas but expands"
            " space behind the defensive line; the net defensive efficiency traces a curve"
            " where moderate pressing intensity minimizes opponent xG/shot conceded."
        ),
        "stat_signature": (
            "PPDA below 7.0 (aggressive press) correlates with opponent transition xG"
            " approximately 0.35-0.50 per 90 above low-press baselines; optimal PPDA"
            " 8-10 minimizes combined high-recovery and transition concession; opponent"
            " xG/shot conceded rises 0.01-0.02 per unit PPDA drop below 8."
        ),
        "mechanism": (
            "High-press intensity requires defensive players to commit forward, vacating"
            " central depth; when the press is beaten, the resultant space behind the"
            " high line yields transition chances with elevated xG/shot because fewer"
            " defenders are goal-side. The curve reflects the exponential cost of being"
            " caught out versus the linear gain from turnovers won."
        ),
        "conditions": (
            "The concession curve steepens against technically proficient opponents capable"
            " of breaking the press with one or two precise vertical passes; it is flatter"
            " against technically limited opponents who cannot execute clean press-escapes"
            " into the space created behind the line."
        ),
        "magnitude": (
            "Moving from PPDA 10 to PPDA 6 against a press-competent opponent increases"
            " transition xG conceded by approximately 0.20-0.35 per 90 while adding"
            " 0.10-0.20 xG from turnovers won high — a structural net concession risk"
            " unless the turnover quality systematically exceeds transition exposure."
        ),
        "links": [
            "pressing_trigger_efficiency_curve",
            "defensive_line_height_xg_tradeoff",
            "attacking_overload_marginal_chance_value",
            "transition_speed_finish_quality_tradeoff",
        ],
    },
    {
        "slug": "crossing_volume_efficiency_decay",
        "title": "Crossing-Volume Efficiency Decay",
        "summary": (
            "Marginal xG per cross falls as crossing volume rises against a packed box;"
            " additional deliveries encounter progressively better-organized aerial defensive"
            " positioning, and the xG-per-cross slope turns negative above a threshold."
        ),
        "stat_signature": (
            "xG per open-play cross approximately 0.032-0.045 at low volumes below 12 per 90;"
            " falls to 0.018-0.028 above 20 per 90 against settled defenses; cross-to-shot"
            " conversion declines from 22-28% at moderate volume to 14-18% at peak volume."
        ),
        "mechanism": (
            "Early crosses exploit defensive displacement before covering players recover"
            " their aerial positions; repeated deliveries allow defenders to read the ball"
            " flight and claim space ahead of attackers. The xG decay reflects the defensive"
            " system accumulating block-and-clear efficiency as cross volume rises."
        ),
        "conditions": (
            "Decay is steepest against physically dominant zonal-marking defenses with tall"
            " central defenders that systematically dominate all aerial challenges;"
            " slowest against man-marking sides that create aerial contest mismatches"
            " when a wide overload draws multiple markers to the ball side."
        ),
        "magnitude": (
            "Increasing from 12 to 22 open-play crosses per 90 against an organized box"
            " yields roughly 0.18-0.25 xG per 90 from the marginal crosses versus"
            " 0.38-0.54 xG from the original 12 — an approximately 55-65% efficiency"
            " discount on the incremental crossing volume."
        ),
        "links": [
            "possession_share_xg_diminishing_returns",
            "territory_to_chance_quality_conversion",
            "set_piece_volume_diminishing_threat",
            "overloaded_zone_marginal_space_value",
        ],
    },
    {
        "slug": "long_range_shot_speculation_curve",
        "title": "Long-Range-Shot Speculation Curve",
        "summary": (
            "As the share of shots attempted outside the penalty area rises, average xG/shot"
            " collapses toward the league minimum; the speculation curve describes the aggregate"
            " quality cost of relying on outside-box attempts to build shot totals."
        ),
        "stat_signature": (
            "Outside-box share above 40% depresses team xG/shot to approximately 0.07-0.09;"
            " below 25% outside-box share, xG/shot reaches 0.11-0.14; each 5-point increase"
            " in outside-box share reduces xG/shot by approximately 0.006-0.010."
        ),
        "mechanism": (
            "Shots from beyond 18 yards face a goalkeeper with full positional advantage and"
            " reaction time; xG values of 0.03-0.05 for these attempts structurally dilute"
            " the mean when volume grows. Sides accumulating outside-box shots at high rates"
            " typically reflect failed penetration attempts rather than deliberate speculation."
        ),
        "conditions": (
            "Outside-box share inflates most against compact deep-block defenses that"
            " successfully prevent central penetration; the curve steepens further when"
            " the side also concedes high transition xG, as rushing speculative shots"
            " trades positional security for illusory volume."
        ),
        "magnitude": (
            "A 15-point rise in outside-box shot share at 15 shots per 90 costs approximately"
            " 0.10-0.15 xG/shot, reducing total xG by roughly 1.5-2.2 per 90 while shot"
            " totals remain constant — among the largest per-shot quality leaks in team attacking."
        ),
        "links": [
            "chance_volume_quality_tradeoff_curve",
            "shot_selection_efficient_frontier",
            "xg_per_shot_volume_elasticity",
            "game_state_chasing_quality_collapse",
        ],
    },
    {
        "slug": "attacking_overload_marginal_chance_value",
        "title": "Attacking-Overload Marginal-Chance Value",
        "summary": (
            "Committing additional attackers forward raises chance creation up to a threshold"
            " beyond which marginal quality falls while counter-attack xG conceded rises;"
            " the net attacking-overload curve peaks at a tactical depth balance point."
        ),
        "stat_signature": (
            "Net xG differential (created minus conceded) peaks at 3-4 attackers committed"
            " into the penalty area per crossing action; above 4 committed attackers,"
            " counter-attack xG conceded rises 0.04-0.08 per additional forward committed;"
            " the marginal xG creation from a fifth committed attacker is near zero."
        ),
        "mechanism": (
            "Additional attackers in the box create aerial and positional competition"
            " for defenders but also open wide-channel space for counter-attacks;"
            " at the overload peak the defensive compactness benefit reverses as"
            " midfield depth becomes insufficient to delay transition. The marginal"
            " creation value of the fifth forward committed is captured by defensive re-positioning."
        ),
        "conditions": (
            "The net-xG peak shifts upward (more attackers beneficial) against fragile"
            " counter-attacking opponents with slow center-backs; it shifts downward against"
            " sides with explosive forward mobility that can exploit any depth conceded."
        ),
        "magnitude": (
            "Over-committing a fifth attacker beyond the optimal balance point costs"
            " approximately 0.06-0.12 net xG per 90 in increased counter-attack exposure"
            " while yielding essentially zero additional created xG — a structural inefficiency"
            " in late attacking phases that recurs across high-pressure game states."
        ),
        "links": [
            "shot_selection_efficient_frontier",
            "press_intensity_chance_concession_curve",
            "transition_speed_finish_quality_tradeoff",
            "game_state_chasing_quality_collapse",
        ],
    },
    {
        "slug": "game_state_chasing_quality_collapse",
        "title": "Game-State Chasing Quality Collapse",
        "summary": (
            "Trailing-state urgency systematically raises shot volume while depressing"
            " xG/shot through forced speculative attempts; the collapse is measured as"
            " the xG/shot drop per minute of accumulated deficit pressure after the hour mark."
        ),
        "stat_signature": (
            "xG/shot while trailing by one after 60 minutes drops approximately 0.018-0.030"
            " below level-state baseline; shot volume rises 20-35% but xG per 90 rises only"
            " 0.05-0.12 — well below the proportional volume increase; per-attempt quality"
            " approaches the outside-box speculation baseline by minute 80."
        ),
        "mechanism": (
            "Trailing teams push higher lines and wider buildup to generate crossing volume,"
            " both of which systematically reduce the central-box shot share that carries"
            " the highest xG/shot; urgency also produces premature long-range attempts rather"
            " than waiting for central positions, reinforcing the quality collapse."
        ),
        "conditions": (
            "Collapse is sharpest when trailing by one in minutes 70-85, where the scoreline"
            " pressure is maximal but substitution-inflicted defensive fragility in opponents"
            " has not yet fully opened space; less severe when trailing by two where tactical"
            " risk acceptance was already priced in from the 60th minute."
        ),
        "magnitude": (
            "A side chasing a deficit from minute 70 adds approximately 3-5 shots per 90"
            " (pro-rated) at 0.015-0.025 lower xG/shot, netting at best 0.05-0.08 additional"
            " xG per 90 from the volume increase — a poor return on the defensive exposure conceded."
        ),
        "links": [
            "long_range_shot_speculation_curve",
            "attacking_overload_marginal_chance_value",
            "tempo_pace_chance_quality_tradeoff",
            "stamina_xg_output_decay_curve",
        ],
    },
    {
        "slug": "tempo_pace_chance_quality_tradeoff",
        "title": "Tempo-Pace Chance-Quality Tradeoff",
        "summary": (
            "Higher attacking tempo trades chance volume against the quality of the average"
            " chance created; fast-tempo sides generate more total attempts but at lower"
            " average xG because positional structure is less complete at delivery."
        ),
        "stat_signature": (
            "Sides above 65 possessions per 90 average xG/shot approximately 0.09-0.11;"
            " sides below 50 possessions per 90 average 0.11-0.14; total xG per 90"
            " correlation with possessions per 90 is near zero (r approximately 0.05-0.12),"
            " indicating volume and quality roughly offset."
        ),
        "mechanism": (
            "High tempo shortens possession sequences, reducing time for supporting runs"
            " to find central positions; the resulting shot attempts are taken from less"
            " optimal spatial positions even when distance is similar, lowering xG per attempt."
            " The tradeoff is near-balanced at the portfolio level, suggesting tempo is a"
            " stylistic rather than efficiency-determining dimension."
        ),
        "conditions": (
            "Tempo advantage is concentrated in transitions against high lines; in settled"
            " phase play against low blocks, high tempo recycling produces diminishing"
            " quality with no spatial advantage because defenses are organized on every attempt."
        ),
        "magnitude": (
            "A 15-possession-per-90 tempo increase raises shot volume approximately 15-20%"
            " but reduces xG/shot by 0.015-0.025, yielding a near-neutral total-xG change"
            " of -0.05 to +0.10 per 90 — consistent with the efficiency curve being the"
            " binding constraint rather than raw tempo."
        ),
        "links": [
            "buildup_directness_quality_tradeoff",
            "xg_per_shot_volume_elasticity",
            "transition_speed_finish_quality_tradeoff",
            "chance_volume_quality_tradeoff_curve",
        ],
    },
    {
        "slug": "central_versus_wide_progression_efficiency",
        "title": "Central-Against-Wide Progression Efficiency Curve",
        "summary": (
            "Central and wide progression channels trace different efficiency curves as"
            " volume in each channel rises; central progression degrades faster under"
            " defensive loading while wide overloads create crossing opportunities at"
            " diminishing xG returns."
        ),
        "stat_signature": (
            "Central progressive carries yield xG per entry approximately 0.055-0.080"
            " at low volume but fall to 0.025-0.040 when central volume exceeds 18 per 90;"
            " wide entries yield 0.020-0.030 xG per entry with slower degradation across volume;"
            " xG-per-entry gap between channels narrows from 0.030 to under 0.010 at high volume."
        ),
        "mechanism": (
            "Central channels are defended with higher priority and density; additional central"
            " entries encounter double-coverage and narrower passing lanes, accelerating the"
            " quality decline. Wide entries maintain moderate efficiency longer because defensive"
            " shape must choose between tracking wide runs and maintaining central compactness."
        ),
        "conditions": (
            "The channel efficiency gap is widest against narrow mid-block defenses that"
            " sacrifice wide coverage to protect the central corridor; it collapses against"
            " wide-press systems that maintain full-pitch coverage through high-energy defensive work."
        ),
        "magnitude": (
            "Rebalancing 5 central progressive entries per 90 toward wide entries when"
            " the central channel is saturated above 18 per 90 recovers approximately"
            " 0.06-0.12 xG per 90 by escaping the steepest portion of the central degradation curve."
        ),
        "links": [
            "territory_to_chance_quality_conversion",
            "buildup_directness_quality_tradeoff",
            "crossing_volume_efficiency_decay",
            "overloaded_zone_marginal_space_value",
        ],
    },
    {
        "slug": "defensive_line_height_xg_tradeoff",
        "title": "Defensive-Line-Height xG Tradeoff",
        "summary": (
            "A higher defensive line compresses opponent buildup space and raises recovery"
            " speed against low-xG attempts, but the in-behind space conceded elevates"
            " the quality of chances created when the line is beaten."
        ),
        "stat_signature": (
            "Each 5-yard rise in average defensive-line height reduces opponent xG from"
            " buildup-phase shots by approximately 0.05-0.10 per 90 but raises in-behind"
            " transition xG conceded by 0.04-0.08 per 90; net xG impact near zero at"
            " optimal line heights of 40-48 yards from own goal in top divisions."
        ),
        "mechanism": (
            "A high line forces opponent buildup into backward passes and reduces time"
            " on ball in dangerous zones; however, the same geometry opens vertical space"
            " that a single penetrating pass can exploit for a 1-against-1 at high xG."
            " Goalkeeper sweeping range sets the practical upper bound for sustainable line height."
        ),
        "conditions": (
            "The tradeoff is most exposed against opponents with pace and comfort playing"
            " in behind; against technically limited opponents unable to execute diagonal"
            " in-behind deliveries, the high-line benefit outweighs the concession risk."
        ),
        "magnitude": (
            "Pushing the defensive line 8 yards higher than optimal against a press-resistant"
            " opponent concedes approximately 0.12-0.18 additional in-behind xG per 90"
            " while recovering only 0.08-0.12 from compressed buildup — a structural net"
            " concession risk of 0.04-0.06 xG per 90 from mismatched line height selection."
        ),
        "links": [
            "press_intensity_chance_concession_curve",
            "pressing_trigger_efficiency_curve",
            "transition_speed_finish_quality_tradeoff",
            "attacking_overload_marginal_chance_value",
        ],
    },
    {
        "slug": "pressing_trigger_efficiency_curve",
        "title": "Pressing-Trigger Efficiency Curve",
        "summary": (
            "The ratio of high ball-recoveries to line-breaks conceded traces an inverted-U"
            " curve across press-trigger frequency; moderate trigger rates maximize the"
            " recovery-to-exposure ratio while very high trigger rates shift the curve"
            " toward concession as gaps become exploitable."
        ),
        "stat_signature": (
            "High recoveries per defensive action peak at trigger frequencies of 18-24"
            " per 90; above 28 triggers per 90 line-breaks conceded rise 25-40% while"
            " marginal recovery gains fall; recovery-to-line-break ratio drops from"
            " approximately 3.5:1 at optimal to 2.0:1 at excessive trigger frequency."
        ),
        "mechanism": (
            "Each pressing trigger commits players to a local ball-hunt; moderate triggers"
            " coincide with genuine opponent vulnerability (back-pass to goalkeeper, misplaced"
            " touch); excessive triggers occur on passes that are not vulnerable, creating"
            " momentum that cannot be braked before the opponent plays through the press."
        ),
        "conditions": (
            "Curve degradation at high trigger rates is sharpest against technically superior"
            " opponents comfortable under pressure; the curve is flatter against technically"
            " limited opponents where a high trigger rate consistently creates genuine vulnerability."
        ),
        "magnitude": (
            "Moving from 24 to 32 press triggers per 90 against a press-resistant opponent"
            " reduces the recovery-to-line-break ratio by approximately 1.0-1.5 units,"
            " translating to roughly 0.12-0.20 additional opponent xG per 90 from"
            " structured press exploitation through the expanding gap frequency."
        ),
        "links": [
            "press_intensity_chance_concession_curve",
            "defensive_line_height_xg_tradeoff",
            "stamina_xg_output_decay_curve",
            "transition_speed_finish_quality_tradeoff",
        ],
    },
    {
        "slug": "transition_speed_finish_quality_tradeoff",
        "title": "Transition-Speed Finish-Quality Tradeoff",
        "summary": (
            "Counter-attack speed trades a spatial xG premium from catching the opponent"
            " out of shape against the precision cost of a rushed final action; the optimal"
            " transition time is not the fastest but the speed that maximizes net xG/shot."
        ),
        "stat_signature": (
            "Transitions completed in under 6 seconds yield xG/shot approximately 0.14-0.20"
            " but off-target rates of 28-35%; transitions in 8-12 seconds yield xG/shot"
            " 0.12-0.17 with off-target rates of 22-28%; net xG peaks at approximately"
            " 7-9 seconds from turnover to attempt in elite counter-attacking systems."
        ),
        "mechanism": (
            "Very fast transitions arrive before the defense can recover but also before"
            " attacking runners reach their optimal finishing positions; the rush cost"
            " manifests as poor contact or poor direction choice under time pressure."
            " The 7-9 second window exploits maximum defensive disorganization while"
            " allowing one supportive run to complete before the final action."
        ),
        "conditions": (
            "The optimal timing window narrows against fast-recovering defenses that reach"
            " optimal block shape within 8 seconds; it widens against slow-transition defenses"
            " where even 12-second counters still find structural disorganization."
        ),
        "magnitude": (
            "A counter-attack completing 4 seconds early (4 rather than 8 seconds) costs"
            " approximately 0.025-0.040 xG/shot from rushing while recovering only"
            " 0.01-0.02 from the marginal defensive disorganization advantage — a net"
            " xG cost of 0.005-0.020 per attempt from sub-optimal transition timing."
        ),
        "links": [
            "tempo_pace_chance_quality_tradeoff",
            "attacking_overload_marginal_chance_value",
            "game_state_chasing_quality_collapse",
            "pressing_trigger_efficiency_curve",
        ],
    },
    {
        "slug": "stamina_xg_output_decay_curve",
        "title": "Stamina xG-Output Decay Curve",
        "summary": (
            "Accumulated physical load erodes pressing intensity and chance-creation output"
            " progressively across match thirds; the decay curve is steepest from minute 75"
            " onward and correlates with the high-intensity-distance decline registered in"
            " physical tracking data."
        ),
        "stat_signature": (
            "Team xG per 15 minutes falls from approximately 0.38-0.45 in the first 30"
            " to 0.28-0.35 in minutes 60-75 and 0.22-0.30 in minutes 75-90 for high-intensity"
            " styles; high-intensity-distance per player declines 12-18% from first to final third;"
            " pressing actions per 90 (pro-rated) fall 20-30% in the last 15 minutes."
        ),
        "mechanism": (
            "High-intensity running depletes glycogen and elevates muscle fatigue over time;"
            " pressing systems that rely on coordinated runs off the ball collapse first as"
            " individual players make locally rational decisions to avoid sprints, breaking"
            " the collective pressure system that creates turnovers high. Chance-creation"
            " decay follows as fewer attacking combinations are completed at pace."
        ),
        "conditions": (
            "Decay is sharpest in matches following a congested fixture schedule with fewer"
            " than 4 rest days; flattest in single-week-cycle preparations and for sides"
            " that drop pressing intensity early to preserve late-match physical capacity."
        ),
        "magnitude": (
            "A pressing-intensive side sees xG-per-15-minute output fall approximately 30-40%"
            " from peak to the final 15 minutes — roughly 0.12-0.18 fewer expected goals"
            " in the terminal period than the first-half rate would project, translating"
            " to approximately 4-6 expected goals per season lost to physical decay."
        ),
        "links": [
            "squad_rotation_load_efficiency_curve",
            "pressing_trigger_efficiency_curve",
            "game_state_chasing_quality_collapse",
            "press_intensity_chance_concession_curve",
        ],
    },
    {
        "slug": "squad_rotation_load_efficiency_curve",
        "title": "Squad-Rotation Load-Efficiency Curve",
        "summary": (
            "Fixture congestion and accumulated minutes load depress attacking efficiency"
            " in proportion to rest days available; the curve describes how xG-per-90"
            " responds to the physical depletion signal captured by cumulative high-intensity"
            " load between matches."
        ),
        "stat_signature": (
            "xG per 90 is approximately 8-15% lower with fewer than 3 rest days than with"
            " 6-plus rest days across comparable match contexts; total distance covered"
            " falls 3-6% and high-intensity running 10-18% with 2-day rest; the efficiency"
            " decay stabilizes above 5 rest days with diminishing recovery returns above 7."
        ),
        "mechanism": (
            "Insufficient recovery between fixtures leaves residual neuromuscular fatigue"
            " that reduces sprint initiation frequency and attacking combination sharpness;"
            " sides rotating squads to manage load sacrifice positional coherence between"
            " rotated and established pairings, reducing combination-play xG."
        ),
        "conditions": (
            "The load curve is steepest in congested midwinter periods with 3 fixtures"
            " in 8 days; it is shallowest for squads with a deep uniform-quality rotation"
            " that can substitute without xG loss. Intensity-management tactical shifts"
            " (conceding possession to recover without the ball) partially offset the curve."
        ),
        "magnitude": (
            "A 10% xG-per-90 decline across a 4-match congested period at 1.40 base xG"
            " per 90 costs approximately 0.56 xG per match or roughly 2.2 xG across the"
            " congested block — equivalent to approximately 1.5-2.0 expected-points lost"
            " from physical depletion alone over the schedule."
        ),
        "links": [
            "stamina_xg_output_decay_curve",
            "chance_volume_quality_tradeoff_curve",
            "pressing_trigger_efficiency_curve",
            "possession_share_xg_diminishing_returns",
        ],
    },
    {
        "slug": "overloaded_zone_marginal_space_value",
        "title": "Overloaded-Zone Marginal-Space Value",
        "summary": (
            "Stacking additional attackers into one zone produces diminishing xG-per-touch"
            " returns as defensive density in that zone rises proportionally; the marginal"
            " space value of an additional attacker turns negative once defenders outnumber"
            " attackers plus one in the targeted zone."
        ),
        "stat_signature": (
            "xG per touch in the penalty area falls from approximately 0.18-0.24 at a"
            " 3-against-2 attacker-to-defender ratio to 0.09-0.13 at 3-against-3 and"
            " 0.05-0.08 at 3-against-4; marginal xG per additional attacker in an already"
            " loaded zone is approximately -0.02 to +0.01 against equal-density defenses."
        ),
        "mechanism": (
            "Each additional attacker draws a covering defender whose marginal contribution"
            " reduces available shooting lanes and passing corridors; beyond the defensive-parity"
            " point the zone becomes increasingly congested, and the chance-quality advantage"
            " of additional bodies is outweighed by the reduced space for any single attacker"
            " to receive a clean touch and execute a high-quality finish."
        ),
        "conditions": (
            "Diminishing returns accelerate when the defensive side shifts cover-shadow"
            " positioning to deny passing into the zone as well as occupying it;"
            " they slow when the attacking overload is asymmetric enough to pin a defender"
            " on one side while creating an uncontested receiver on the other."
        ),
        "magnitude": (
            "Adding a fourth attacker to a 3-attacker zone facing 3 defenders yields"
            " approximately zero net xG gain; adding a fifth against 4 defenders produces"
            " an estimated -0.01 to -0.03 xG per 90 net from the congestion cost exceeding"
            " the space-creation benefit — confirming the overload threshold as a hard constraint."
        ),
        "links": [
            "attacking_overload_marginal_chance_value",
            "territory_to_chance_quality_conversion",
            "central_versus_wide_progression_efficiency",
            "crossing_volume_efficiency_decay",
        ],
    },
]
