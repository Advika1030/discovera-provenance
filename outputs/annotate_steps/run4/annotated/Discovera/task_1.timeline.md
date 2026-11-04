# Task 1: timeline

| step | tool | step_description | status |
|---|---|---|---|
| 1 | csv_read | Step 0b: Preview the uploaded differential protein CSV to locate gene and statistic columns before shaping/enrichment. | ok |
| 2 | csv_select | Step 3: Select gene and statistics columns to prepare a gene-level table for enrichment ('Gene' plus L2FC, T-Score, P-Val, FDR). | ok |
| 3 | csv_filter | Step 0b: Check presence of candidate genes (CTNNB1, AXIN1, LEF1, GSK3B, APC) in the selected gene list (case-sensitive exact match where present). | ok |
| 4 | csv_filter | Step 3: Filter the selected table to significant proteins (FDR < 0.05) for ORA and direction summaries. | ok |
| 5 | csv_filter | Step 3: Create 'Upregulated' subset (L2FC > 0 and FDR < 0.05) for direction-specific ORA. | ok |
| 6 | csv_filter | Step 3: Create 'Downregulated' subset (L2FC < 0 and FDR < 0.05) for direction-specific ORA. | ok |
| 7 | csv_aggregate | Step 3: Aggregate numeric columns to produce a mean L2FC column (row-wise mean across the L2FC column) to check aggregation tools and preserve a standard input shape for enrichment tools. | ok |
| 8 | gsea_pipe | Step 4: Run preranked GSEA on the mean_L2FC-ranked protein list to identify pathways altered in CTNNB1-hotspot vs WT (use Gene as hit and L2FC as ranking metric). | ok |
| 9 | ora_pipe | Step 4: Run ORA (Enrichr-style) on the FDR<0.05 significant protein list to capture over-represented pathways/terms (gene column 'Gene'). | ok |
| 10 | csv_read | Step 4b: Preview the ORA results CSV to identify column names for keyword filtering. | ok |
| 11 | csv_filter | Step 4b: Filter ORA results for entries listing CTNNB1 in the 'Genes' column (keyword-driven subset for CTNNB1-related terms). | ok |
| 12 | csv_filter | Step 4b: Filter ORA results for entries listing AXIN1 in the 'Genes' column (keyword-driven subset for AXIN1/WNT-related terms). | ok |
| 13 | csv_read | Step 4b: Preview the full GSEA results CSV to extract top terms and leading-edge genes for Wnt/CTNNB1 relevance. | ok |
| 14 | csv_filter | Step 5: Extract GSEA row(s) for 'Wnt' pathways to obtain leading-edge genes for leading-edge analysis. | ok |
| 15 | gene_info | Step 5: Retrieve gene annotations for leading-edge Wnt genes to support mechanistic interpretation (CTNNB1, AXIN1, LEF1, TCF7, DKK1, DKK4, WIF1, CCND1). | ok |
| 16 | sets_info_rumm | Step 5: Retrieve gene membership and annotations for the enriched Wnt KEGG gene set (to confirm leading-edge composition). | error |
| 17 | sets_info_rumm | Step 5: Retrieve gene membership for Reactome term 'CTNNB1 S45 Mutants Aren'T Phosphorylated' to inspect which proteins drive this ORA signal. | error |
| 18 | enrich_rumma | Step 5: Run Rummagene enrichment on leading-edge Wnt genes to validate pathway themes (CTNNB1, AXIN1, LEF1, TCF7, DKK1, DKK4, WIF1, CCND1). | ok |
| 19 | query_string_rumma | Step 6: PubMed/Rummagene search for CTNNB1 S45 phosphorylation in endometrial carcinoma to tie phosphosite observation to literature. | ok |
| 20 | query_table_rumma | Step 6: Search Rummagene gene-set tables for 'CTNNB1 S45' to extract linked PMCIDs/pmids for CTNNB1 phosphosite literature. | empty |
| 21 | query_table_rumma | Step 6: Search Rummagene gene-set tables for 'CTNNB1' to extract linked PMCIDs/pmids for CTNNB1 literature. | ok |
| 22 | literature_trends | Step 6: Plot PubMed publication timeline for 'CTNNB1 endometrial carcinoma' to contextualize literature trends. | ok |
| 23 | prioritize_genes | Step 6: Prioritize candidate genes in the context of 'endometrial carcinoma CTNNB1 mutation' using PubMed evidence. | ok |
| 24 | query_string_rumma | Step 6: Find PubMed/PMCID for the S45F β-catenin paper observed in query matches to obtain a PMID for citation. | ok |
| 25 | gene_info | Step 5: Fetch gene annotations for two downregulated proteins observed in the data (PFN1, HCLS1) to support the Down table. | ok |
