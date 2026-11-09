#!/usr/bin/env Rscript
# Who has been the median justice of the MAJORITY COALITION, by term?
#
# Not the Court median: the median of the justices who actually joined the
# winning side in each case. Those differ whenever the majority is lopsided --
# in a 9-0 the coalition median IS the Court median, in a 5-4 it is the fifth
# vote.
#
# Method
#   universe   formally decided merits cases, one row per justice vote
#   coalition  majority == 2 (voted with the majority)
#   ideology   JCS justice-term scores (so the same justice moves with the term)
#   median     sort the coalition by jcs; odd n -> the middle justice gets 1
#              credit, even n -> the two middle justices get 0.5 each
#   dropped    cases where any coalition member has no JCS score for that term
#
# Run from the skill root:   Rscript scripts/coalition_median.R

source("scripts/scdb.R")

v <- scdb_add_jcs(scdb_merits_votes(scdb_formally_decided(scdb_load("justice"))))

# the winning coalition, keeping only cases where every member is scored
co <- v[!is.na(v$majority) & v$majority == 2, ]
all_scored <- tapply(!is.na(co$jcs), co$caseId, all)
co <- co[all_scored[as.character(co$caseId)], ]

# rank each coalition from most liberal to most conservative
co <- co[order(co$caseId, co$jcs, co$justiceName), ]
n <- ave(co$jcs, co$caseId, FUN = length)                  # coalition size
r <- sequence(rle(as.character(co$caseId))$lengths) - 1    # 0-based rank

# median credit: 1 to the middle, or 0.5 to each of the two middles
co$w <- ifelse(n %% 2 == 1,
               as.numeric(r == n %/% 2),
               0.5 * ((r == n %/% 2 - 1) | (r == n %/% 2)))

cat(sprintf("%d cases, OT%d-OT%d, %d terms\n\n",
            length(unique(co$caseId)), min(co$term), max(co$term),
            length(unique(co$term))))

# ---- per term: who held the coalition median most often
by_tj <- aggregate(w ~ term + justiceName, data = co, FUN = sum)
by_tj <- by_tj[by_tj$w > 0, ]
cases <- tapply(co$w, co$term, sum)                        # == cases per term
top <- do.call(rbind, lapply(split(by_tj, by_tj$term), function(d)
  d[order(-d$w, d$justiceName), ][1, ]))
top$cases <- as.numeric(cases[as.character(top$term)])
top$share <- round(100 * top$w / top$cases)
top <- top[order(top$term), c("term", "justiceName", "w", "cases", "share")]
print(top, row.names = FALSE)

# ---- collapse consecutive terms into eras
run <- cumsum(c(TRUE, top$justiceName[-1] != head(top$justiceName, -1)))
era <- do.call(rbind, lapply(split(top, run), function(d) data.frame(
  justice = d$justiceName[1], from = min(d$term), to = max(d$term),
  terms = nrow(d), cases = sum(d$cases), credit = sum(d$w),
  share = round(100 * sum(d$w) / sum(d$cases)))))
cat("\n-- eras --\n"); print(era, row.names = FALSE)

# ---- two rankings
cat("\n-- terms as the modal coalition median --\n")
print(sort(table(top$justiceName), decreasing = TRUE))

cat("\n-- total median credit, all terms --\n")
tot <- aggregate(w ~ justiceName, data = co, FUN = sum)
print(head(tot[order(-tot$w), ], 15), row.names = FALSE)
