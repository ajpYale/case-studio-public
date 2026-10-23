# Quality rules (learned from auditing 300+ published casebook cases)

About a third of real casebook cases had a flaw serious enough to drop them. These are the
failure patterns that came up again and again. A generated case must avoid every one.

## Answer-key arithmetic
- Every stated result must equal the computation from the case's own data. Never round an
  intermediate number and then use the rounded number as if exact, unless the case says to.
- Watch time bases: "revenue over five years" is five years of revenue, not one; per-day vs
  per-hour vs per-year; one-time costs vs annual costs.
- Watch stock vs flow: babies born per year vs babies in an age band; installed base vs annual sales.

## Internal consistency
- The prompt, clarifying answers, exhibits, and answer key must agree on every number (the
  most common flaw: the exhibit says 500 and the key uses 640).
- Exhibit totals must equal the sum of their components; pie charts must sum to 100%.
- Column and unit labels must match the values ($M vs $B, % vs points, per unit vs total).
- Qualitative claims in the key ("the only growing segment", "economy share rose") must match
  what the exhibit actually shows.
- Don't reuse text from another scenario: every recommendation must be about this client.

## Method
- Never treat revenue as profit. If profit is asked, the case must give (or let the candidate
  assume) the costs, and the key must subtract them.
- Never compare undiscounted multi-year profit with a price paid today as if equivalent. Either
  give a discount rate and discount, or state explicitly that the case ignores time value.
- Don't add up mutually exclusive options. Don't double count the same units or dollars.
- Don't ignore a cost or constraint that the case itself provides (capacity, fixed cost, tax).
- Margin is profit / price, markup is profit / cost — don't mix them up.
- Breakeven, payback, NPV, CAGR, market share and percentage-point changes must use the
  standard definitions.

## Finance (where generated cases most often slip)
- Enterprise value vs equity value: if the asking price is an enterprise value, compare it to
  enterprise value; subtract net debt only when moving to equity value, and only once.
- Perpetuities: a flat annual cash flow C is worth C / r; a growing one is C x (1 + g) / (r - g).
  Use the one the case describes, and state r (and g).
- Treat options the same way: if one option is risk-adjusted, discounted, or taxed, the options
  it's compared against must be too, or the case must say why not.
- If a calculation needs a schedule (capex by year, ramp-up by year), the exhibit must show the
  schedule, not just its total.
- Define cash flow once (before or after capex, before or after tax) and keep to it.
- Growth rates compound; never add two years' growth rates together.
- If the case tells the candidate to use a rounded factor (an annuity factor of 3.8x, a discount
  factor of 0.9), make it a variable and use that variable in the calculations — never the exact
  formula — so the candidate can reproduce the key.
- State timing conventions the math depends on: when capex is paid (today, year 0), when cash
  flows start, whether a ramp-up applies, and whether a perpetuity starts after year N.
- Compare options at the volume each one can actually serve, and say which caps apply to which
  option (demand, capacity, contract limits).
- Calendars and capacities must be physically possible (no month with 32 days, no utilization
  above 100%).
- A "discount to asking" must be positive when the offer is below asking; say "premium" otherwise.
- Applying a percentage constraint (e.g. only 60% of sites can be upgraded) to a total only works
  if the total scales with that base; otherwise apply it where it bites.

## Premise
- Real named companies, markets, laws, and technologies must be described accurately. Prefer a
  client with an invented name in a real industry, presented as real (never labelled fictional). Don't invent "new" technologies that are decades old, don't
  misstate regulations, and keep medical/scientific facts correct.
- Magnitudes should be plausible (a regional chain doesn't have $30B of revenue; 10 million
  convenience stores don't exist in the US).

## Runnability
- Every number the candidate needs must be available from the prompt, a clarifying answer, an
  exhibit, or an explicit "assume" instruction. No answer may depend on data the case never gives.
- Each section's question must connect to the client's core question.
- The recommendation must follow from the numbers the candidate computed.
- A "per unit of resource" comparison (contribution per staff hour, per machine hour, per square
  foot, per truck) only decides anything if that resource is the binding constraint. If the
  insight rests on it, the case must establish the constraint (limited hours, full capacity, a
  fixed fleet) and show it binds; otherwise compare total contribution instead.
- Every assumption the answer depends on (constant volumes over time, the same cost base next
  year, cash-flow timing, what happens if an option is declined) must be stated to the
  candidate, not left implicit in the key.
- Give the interviewer enough guidance to run the case: what to share when, what a strong answer
  looks like, hints, and where candidates go wrong.
