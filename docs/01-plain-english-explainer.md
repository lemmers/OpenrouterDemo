# OpenRouter Case Study: Plain English Explainer

## How to use this document

This explains the case study in ordinary language. It assumes you know how software and APIs work in general, and assumes nothing about AI terminology. Where a term is jargon it gets defined the first time and then used normally, because you need to be able to say these words comfortably in the room.

Read it in order. Sections 3 through 5 build the mental model. Section 6 onward is the actual case. If you only have ten minutes before the interview, read section 2 and section 10.

One thing worth saying plainly: you do not need to be an engineer to win this. You need to understand the shape of the problem well enough to ask the right questions, spot the flaw in the developer's reasoning, and know which fix applies. That is a customer success skill, not an engineering one.

## The 90 second version

**The situation.** A big customer pays OpenRouter to sit between their software and the AI models they use. Their lead engineer ran a test, decided OpenRouter is making things slower, and emailed you saying so, with his CTO copied. The renewal is 90 days out. He wants to cut OpenRouter out and call Anthropic directly.

**Why he is probably wrong on the facts.** OpenRouter can serve the same AI model through several different suppliers. Unless you tell it otherwise, it spreads your traffic across them. So when he compared OpenRouter against Anthropic direct, he was very likely comparing two different sets of computers in two different data centers. The slowdown he saw is mostly a supplier difference, not a middleman tax. One configuration setting fixes it.

**Why he is partly right anyway.** There is a real cost to going through a middleman. It is small, roughly 30 milliseconds when configured properly, on a response that takes about four seconds end to end. Admit it. Put the number on a slide. Denying it ends your credibility in the first two minutes.

**Why he is asking the wrong question.** He is optimizing for the typical case. His company's product has a service commitment to its own customers, which means the bad cases matter more than the typical ones. Going direct means his team now owns the job of handling failures: what happens when the supplier is full, is throttling you, or is down. The middleman he wants to remove is what handles that today.

**What you propose.** Split the traffic. His one speed critical feature gets pinned to a single supplier, or moves direct if he insists. Everything else stays on OpenRouter, keeps the automatic failure handling, and keeps one bill, one integration and one place to see spending. You give up the small piece to protect the large one.

**What you ask for.** The renewal, plus a 30 day joint test that settles the question with real numbers from their own traffic instead of from a laptop.

## What OpenRouter actually does

Start with what a customer is buying.

A company building an AI product needs to send text to an AI model and get text back, millions of times a day. They could sign a contract with Anthropic and write code that talks to Anthropic. Then they want to try a cheaper model from someone else, so they write a second integration. Then a third. Each one has its own contract, its own bill, its own quirks, its own outages.

OpenRouter sits in the middle of that. You write one integration to OpenRouter, and through it you can reach hundreds of models from dozens of companies. Change which model you use by changing one line of text, not by writing new code.

**The analogy that works.** Think of a freight forwarder. You could contract directly with one shipping line. It is the shortest paper trail and probably the cheapest per container. But if that line's port closes, your freight sits. A forwarder holds contracts with many lines, books you on whichever is moving, and reroutes when one goes down. You pay a margin for that. The margin is not the service, the rerouting is the service.

That is the whole argument you are about to have. The developer is looking at the margin. You need to get the CTO looking at the rerouting.

**What OpenRouter adds on top of the basic relay:**

- If a supplier fails or is full, it retries somewhere else automatically, so the request still completes
- One bill instead of a dozen, and one place to see which team is spending what
- Controls over where data is allowed to go, which matters for regulated customers
- You can plug in your own contract with a supplier and still route through OpenRouter, keeping your negotiated price and your priority access

## The one distinction everything hinges on

If you take one thing from this document, take this.

**A model is not the same thing as a provider.**

The *model* is the AI itself. Claude Sonnet, for example. It is a specific trained system with specific behavior.

The *provider* is the company running that model on its computers and answering your request. Claude is available from Anthropic directly, and also from Amazon (through a service called Bedrock) and from Google (through a service called Vertex). Same model, same answers, three different companies operating three different sets of hardware in three different places.

Why this matters: those three are not equally fast. Different hardware, different data center locations, different amounts of traffic at any moment. The gap between providers is routinely larger than the gap caused by routing through a middleman.

**And here is the part that wins your argument.** Unless you tell OpenRouter which provider to use, it spreads your requests across several of them on purpose, so that one provider having a bad day does not take you down. That is the default and it is a sensible default for most traffic.

But it means a test that compares OpenRouter against Anthropic direct is not comparing a middleman to no middleman. It is comparing a mix of three providers against one specific provider. That is not the experiment the developer thinks he ran.

And it is fixable in one setting. You can tell OpenRouter to use only Anthropic, in which case the comparison becomes apples to apples and the remaining gap is the true cost of the middleman.

## The vocabulary you need

Only the terms that will actually come up. Each one has a note on why it matters in this specific conversation.

| Term | Plain meaning | Why it matters here |
| --- | --- | --- |
| Token | A chunk of text, roughly three quarters of a word. Models read and write in tokens, and billing is per million tokens. | Everything is priced and measured in tokens, so you need the unit to talk about cost or speed. |
| Prompt | What you send in. Also called input. | Half the bill. Long prompts cost more and are slower to process. |
| Completion | What the model sends back. Also called output. | The other half, usually priced several times higher than input. |
| Inference | The act of running the model to produce an answer. | Industry word for the thing being bought. Their spend is the inference bill. |
| Streaming | The answer comes back word by word as it is produced, rather than all at once at the end. | The whole latency argument only makes sense in a streaming product, which theirs is. |
| Time to first token | How long from sending the request until the first word appears. | This is the number under dispute. It is what a user experiences as responsiveness. |
| Tokens per second | How fast words come out after the first one. Also called decode speed. | Set entirely by the provider's hardware. A middleman does not change it, which is a fact in your favor. |
| Prompt caching | The provider remembers the front part of a repeated prompt so it does not reprocess it every time. | Turning this on saves far more time than the routing hop costs. It is your best counterpunch. |
| Context window | How much text the model can consider at once. | Background only. Unlikely to come up in this case. |
| Rate limit | The supplier caps how many requests you can send per minute. Go over and you get rejected. | This is the hidden cause of most real world slowness, and the thing the middleman handles for you. |
| 429 | The specific error code for being rate limited. | You will see it in the benchmark data. Say the number and you sound fluent. |
| Failover, or fallback | When one supplier fails, automatically retry at another. | The core of OpenRouter's value. Going direct means building this yourself. |
| Gateway, or router | The middleman layer. OpenRouter is one. | What you are defending. |
| BYOK | Bring your own key. Use your own contract with a supplier, but still route through the gateway. | Lets the customer keep their negotiated discount and priority access while keeping the gateway. Your strongest concession. |
| p50, p95, p99 | The typical case, the bad case, and the worst case. p95 means 95 percent of requests were at least this fast. | The developer is arguing about p50. You need the conversation on p95, because that is what their customers feel. |
| SLA | A contractual promise about service quality. | Their product makes one to their customers. That is why reliability beats milliseconds. |
| Zero data retention | The supplier promises not to keep your text after answering. | A CTO compliance concern, and an area where the gateway helps rather than hurts. |

## The problem statement

**The account.** Kestrel AI builds software for customer support teams. When a support agent is typing a reply, Kestrel's product suggests the answer in real time. It also handles simple tickets automatically. They spend about 4.1 million dollars a year on AI model usage through OpenRouter. The contract renews in December.

**Two very different workloads.** About 8 million requests a month power the live suggestion feature, where a human is sitting there waiting and speed matters. About 34 million requests a month run overnight doing scoring and summarizing, where nobody is waiting and speed is irrelevant. That is roughly one fifth of the volume carrying all of the urgency.

**What happened.** Raj Mehta, their lead engineer, ran a test from his laptop. Two hundred requests through OpenRouter, two hundred straight to Anthropic. He measured OpenRouter as 140 milliseconds slower on average and emailed you calling it unnecessary latency. He copied Dana Whitfield, the CTO.

**What is actually going on.** Three things sit underneath that email, and only one of them is about milliseconds.

1. **A real technical observation, badly measured.** There is a gap. It is smaller than he thinks and mostly caused by something he can fix in one setting.
2. **A bad experience he has not mentioned.** Two weeks before his test, a supplier capacity problem gave his team a rough afternoon. That is the emotional driver. The benchmark came after, looking for a reason.
3. **Nobody left to defend the decision.** The VP of Engineering who originally chose OpenRouter has left the company. Vendors get re-examined when their internal sponsor leaves. This is the actual reason you are having this meeting.

**Why the CTO is copied.** That is not an accident and it is not a technical detail. Copying the CTO converts an engineering opinion into a budget question. Read it as the opening move in a case to cut the vendor, and respond to it as such.

**What you are actually being asked to do.** Give the engineer a technically correct answer he can respect, and give the CTO a reason to keep spending 4.1 million dollars a year. Those are two different arguments for two different people, in the same twenty minutes.

## What he actually measured

Six problems with his test. Never present these as a list of his mistakes. Present them as the things any benchmark of this kind has to control for, and offer to rerun it together. Same content, completely different reception.

**1. He probably compared different suppliers.** Covered in section 4, and it is the big one. His OpenRouter requests were spread across Anthropic, Amazon and Google. His direct requests all went to Anthropic. Most of his 140 milliseconds is that difference, not the middleman.

**2. He ran them in blocks, not alternating.** Two hundred one way, then two hundred the other. Internet performance changes minute to minute. If the second batch ran while the network was busier, that shows up as a difference that has nothing to do with either option. The fix is to alternate: one request each way, back and forth.

**3. He used an average.** An average hides the shape of the data. Ten fast responses and one terrible one average out to something that describes neither. You want p50 and p95 reported separately, because they tell opposite stories here.

**4. Two hundred requests is too few.** For a typical value it is adequate. For the bad cases, which are the ones that matter to a product with a service commitment, it is nowhere near enough.

**5. He may not have matched caching.** If one side benefited from prompt caching and the other did not, the comparison is meaningless, because caching changes speed far more than routing does.

**6. He ran one request at a time.** Real traffic runs hundreds at once. Under real load, the thing that actually slows you down is hitting supplier rate limits, and that is precisely the scenario where spreading across suppliers helps instead of hurts. His test was designed, accidentally, to never show the benefit.

**The one sentence version for the room:** your test measured which supplier answered, not whether the gateway is slow, and I would like to rerun it with you in a way that isolates that.

## The proposed solution, piece by piece

Five parts. Parts one through three are for the engineer. Parts four and five are for the CTO.

**1. Pin the fast path to one supplier.**

Tell OpenRouter to use only Anthropic for the live suggestion feature, and not to substitute anyone else. Their traffic stops bouncing between suppliers, performance becomes consistent, and most of the gap he measured disappears. This is a configuration change, not a project. It is the thing you can offer to do this week, and offering a same week fix changes the whole temperature of the meeting.

The tradeoff to state honestly: pinning to one supplier means giving up automatic rerouting on that traffic. You are trading some resilience for consistency. That is the right trade for this particular feature and the wrong trade for the rest.

**2. Turn on prompt caching.**

Most of their requests start with the same long block of instructions. Caching lets the supplier skip reprocessing it. In the sample data this cut time to first token by about 235 milliseconds. He is fighting over 30. This single slide reframes the meeting: you are chasing 30 milliseconds while leaving 235 on the table.

**3. Agree a proper test.**

Alternating requests, same region, matched caching, supplier pinned, at least 500 each way, run across a full working day at real load. Report the typical case and the bad case separately, plus the failure rate. Thirty days, his engineer and yours, and you both sign the result. This turns an argument into a joint project and makes him a participant rather than an opponent.

**4. Let them go direct where it genuinely makes sense.**

Say out loud that for the live suggestion feature, going direct is a reasonable choice, and you will help them do it if that is what they want. This costs you one fifth of the volume and buys you enormous credibility. Nobody believes a vendor who says never go direct. And it removes the all or nothing framing that is currently the biggest threat to the renewal.

**5. Protect the other four fifths on its actual merits.**

For the overnight workload, where speed does not matter at all, the gateway gives them cheaper suppliers, automatic recovery from failures, one bill, and visibility into which team spends what. None of that is about latency, and latency was never the real question for that traffic.

Offer bring your own key as the bridge: Kestrel keeps their own Anthropic contract and discount, and still routes through OpenRouter. They stop paying a middleman markup on inference they have already negotiated, and they keep the failure handling. It is the answer to the fee objection before it is raised.

## What the numbers mean in English

From the sample dataset. These are modeled figures, not measurements, and any slide built from them needs to say so.

**Finding 1. Pinning fixes most of it.** Spread across suppliers, the gateway cost 70 to 138 milliseconds in the typical case. Pinned to Anthropic, it cost 28 to 53, and in the heavy load run it came out slightly faster than going direct. Plain version: almost everything he complained about was the supplier lottery, not the gateway, and it is one setting.

**Finding 2. The gateway does not slow the words down.** Once the answer starts, text came back at about 65 tokens per second on all three setups. Plain version: the middleman passes the stream through untouched. This kills the suspicion that OpenRouter is throttling them, which is the version of this objection that would be genuinely damaging.

**Finding 3. The disputed amount is one to three percent of the wait.** A full response takes around 3.9 seconds. The routing hop is roughly 30 milliseconds of that. Plain version: he is arguing about the last one percent of a four second wait.

**Finding 4. Caching matters fifteen times more.** Warm caching cut time to first token from 373 milliseconds to 138. That is a 235 millisecond saving available today, against a 28 millisecond cost he wants to eliminate. Plain version: there is a much bigger win sitting untouched, and I can help you take it.

**Finding 5. This is where it flips.** Under heavy load, going direct failed on 4.0 percent of requests. Pinned with no substitution allowed failed on 2.5 percent. Spread across suppliers failed on 0.5 percent. In the modeled outage: 20.5 percent, 11.0 percent, and 0.5 percent.

Plain version, and this is the sentence to land: spreading across suppliers costs you about 78 milliseconds in the typical case and prevents roughly forty times as many failed requests. That is the actual trade. State it in both directions, because saying the cost out loud is what makes the benefit believable.

**A trap to know about.** There are two ways to measure the start of a response: when the first bytes of any kind arrive, and when the first actual word arrives. On the routed setup the connection opens sooner, so measuring the first kind makes the gateway look better than it is. Use the real one, and say why you are using it. If you do not raise this, the developer may, and then it looks like you were hiding it.

## The business case, and what to memorize

### For the CTO, in her terms

**What building it themselves actually costs.** Going direct means Kestrel's own engineers now write and maintain the retry logic, the failure handling, the spend tracking, and the per supplier integrations. They will still be maintaining it in two years. Ask what that engineering time is worth against the fee, and let her do the arithmetic herself rather than doing it for her.

**Being able to change your mind.** Model prices have fallen repeatedly, and better models keep arriving. Today swapping models is a configuration change. Directly integrated, it becomes a project every time. She is not buying speed, she is buying the ability to move when the market moves.

**The cost of one bad afternoon.** Their product carries a service commitment to enterprise contact centers. Weigh one breach of that against the milliseconds under discussion.

**Control over data.** They can restrict which suppliers are allowed, require suppliers that do not retain their text, and keep processing in a specific region. That is an easier compliance story through one gateway than across four separate contracts.

### Six sentences to memorize

1. Your test compared different suppliers, not the gateway. That is one setting and I can change it this week.
2. Yes, there is a real cost to routing. Configured properly it is about 30 milliseconds on a four second response.
3. The gateway does not slow the stream down. Your words come back at the same speed either way.
4. Caching will save you eight times more than removing us would.
5. Spreading across suppliers costs you about 78 milliseconds and prevents roughly forty times as many failed requests. That is the trade.
6. Go direct on the live suggestion feature if that is right for you. I want to talk about the other four fifths of your traffic.

### Things to have an answer for

- **The Stripe acquisition.** Stripe agreed to acquire OpenRouter in August 2026. A CTO will ask what it means for roadmap, pricing and neutrality. Do not pretend it did not happen and do not speculate past what is public.
- **Why not build it ourselves.** Scope it honestly rather than dismissing it. Integrations, retries, failover, spend attribution, observability, and someone on call.
- **Your failover chart is not a real outage.** Agree immediately, say it is modeled, and offer to instrument the real thing over the next 30 days. Conceding fast here builds more trust than any slide.

### The last thing

Ask for the renewal out loud, with a date and an owner. Most candidates spend twenty minutes being right and never actually ask.
