"""
Architecture diagram for Requirements Management AI
Mirrors the style of the reference image: dashed group boxes, colored service
boxes, labelled arrows, AWS-account boundary.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig, ax = plt.subplots(figsize=(26, 18))
ax.set_xlim(0, 26)
ax.set_ylim(0, 18)
ax.axis("off")
fig.patch.set_facecolor("#FAFAFA")

# ── Helpers ───────────────────────────────────────────────────────────────────

def box(x, y, w, h, fc, ec, lw=1.2, radius=0.25, alpha=1.0):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle=f"round,pad=0.05,rounding_size={radius}",
                                facecolor=fc, edgecolor=ec, linewidth=lw, alpha=alpha,
                                zorder=3))

def dashed_box(x, y, w, h, ec, label="", fc="none", lw=1.4):
    ax.add_patch(mpatches.FancyBboxPatch((x, y), w, h,
                                          boxstyle="round,pad=0.1,rounding_size=0.3",
                                          facecolor=fc, edgecolor=ec,
                                          linewidth=lw, linestyle="--", zorder=2))
    if label:
        ax.text(x + 0.18, y + h - 0.28, label, fontsize=7.5, fontweight="bold",
                color=ec, va="top", zorder=4)

def label(x, y, txt, fs=7.5, color="white", bold=False, ha="center", va="center"):
    ax.text(x, y, txt, fontsize=fs, color=color,
            fontweight="bold" if bold else "normal",
            ha=ha, va=va, zorder=5, wrap=True,
            multialignment="center")

def arrow(x1, y1, x2, y2, lbl="", color="#444", lw=1.3, style="->", lbl_offset=(0, 0.18)):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color,
                                lw=lw, connectionstyle="arc3,rad=0.0"),
                zorder=4)
    if lbl:
        mx, my = (x1 + x2) / 2 + lbl_offset[0], (y1 + y2) / 2 + lbl_offset[1]
        ax.text(mx, my, lbl, fontsize=6.5, color=color, ha="center", va="bottom", zorder=5)

def darrow(x1, y1, x2, y2, lbl="", color="#444", lbl_offset=(0, 0.18)):
    """Double-headed arrow."""
    arrow(x1, y1, x2, y2, lbl, color, style="<->", lbl_offset=lbl_offset)

# ── Colour palette ────────────────────────────────────────────────────────────
C_AWS      = "#FF9900"   # AWS orange
C_BEDROCK  = "#01A88D"   # Bedrock teal
C_LAMBDA   = "#FF9900"
C_S3       = "#3F8624"
C_RDS      = "#2E73B8"
C_OS       = "#8C4FFF"   # OpenSearch purple
C_REDIS    = "#C0392B"   # Redis red
C_NEPTUNE  = "#1A9C3E"
C_APIGW    = "#A020F0"
C_COGNITO  = "#DD344C"
C_CW       = "#FF4F8B"
C_TEXTRACT = "#01A88D"
C_COMPREH  = "#01A88D"
C_REACT    = "#20232A"
C_FASTAPI  = "#009688"
C_AGENT    = "#1A73E8"
C_KG       = "#E67E22"
C_RAG      = "#6C3483"

# ═══════════════════════════════════════════════════════════════════════════════
# 1. AWS ACCOUNT boundary
# ═══════════════════════════════════════════════════════════════════════════════
dashed_box(5.8, 0.4, 19.8, 17.2, ec="#FF4081", label="AWS Account  (us-east-1)", fc="#FFF5F8", lw=2)

# ═══════════════════════════════════════════════════════════════════════════════
# 2. USER  (far left)
# ═══════════════════════════════════════════════════════════════════════════════
box(0.3, 8.5, 1.6, 1.1, "#37474F", "#263238")
label(1.1, 9.05, "Users", fs=8, bold=True)

# ═══════════════════════════════════════════════════════════════════════════════
# 3. UI LAYER
# ═══════════════════════════════════════════════════════════════════════════════
dashed_box(2.2, 6.5, 3.2, 5.2, ec="#1565C0", label="UI Layer", fc="#E3F2FD")

# React frontend
box(2.4, 9.8, 2.8, 1.1, C_REACT, "#111")
label(3.8, 10.35, "React / Vite\nFrontend (TypeScript)", fs=7, bold=True)

# FastAPI backend
box(2.4, 8.2, 2.8, 1.1, C_FASTAPI, "#00695C")
label(3.8, 8.75, "FastAPI Backend\n(SSE Streaming)", fs=7, bold=True)

# Amazon Cognito
box(2.4, 6.8, 2.8, 1.0, C_COGNITO, "#B71C1C")
label(3.8, 7.3, "Amazon Cognito\nUser Auth", fs=7, bold=True)

# ═══════════════════════════════════════════════════════════════════════════════
# 4. API GATEWAY
# ═══════════════════════════════════════════════════════════════════════════════
box(6.2, 8.5, 2.4, 1.0, C_APIGW, "#6A0DAD")
label(7.4, 9.0, "API Gateway\n(REST + CORS)", fs=7, bold=True)

# ═══════════════════════════════════════════════════════════════════════════════
# 5. BEDROCK AGENT (AgentCore)
# ═══════════════════════════════════════════════════════════════════════════════
dashed_box(9.0, 7.2, 5.2, 5.8, ec="#1A73E8", label="AgentCore  (Bedrock Agent)", fc="#E8F0FE", lw=1.8)

box(9.3, 10.8, 4.6, 1.8, C_AGENT, "#0D47A1")
label(11.6, 11.7, "Bedrock Agent\nClaude 3.5 Sonnet v2", fs=8, bold=True)
label(11.6, 11.25, "RequirementsManagementAgent", fs=6.5, color="#BBDEFB")

# Action groups inside agent box
box(9.3, 9.5, 2.1, 1.0, "#1565C0", "#0D47A1")
label(10.35, 10.0, "Document\nProcessor AG", fs=6.5)

box(11.6, 9.5, 2.1, 1.0, "#1565C0", "#0D47A1")
label(12.65, 10.0, "Requirements\nExtractor AG", fs=6.5)

box(9.3, 8.2, 2.1, 1.0, "#1565C0", "#0D47A1")
label(10.35, 8.7, "Expert\nMatcher AG", fs=6.5)

box(11.6, 8.2, 2.1, 1.0, "#1565C0", "#0D47A1")
label(12.65, 8.7, "Compliance\nChecker AG", fs=6.5)

# Knowledge Bases attached to agent
box(9.3, 7.4, 4.6, 0.6, "#283593", "#1A237E")
label(11.6, 7.7, "Knowledge Bases: Requirements KB | Regulatory KB | Experts KB", fs=6.5)

# ═══════════════════════════════════════════════════════════════════════════════
# 6. LAMBDA FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════
dashed_box(6.2, 4.0, 7.8, 3.0, ec="#E65100", label="Lambda Functions (Python 3.11 · VPC · X-Ray)", fc="#FFF3E0")

box(6.4, 4.8, 1.7, 1.0, C_LAMBDA, "#E65100")
label(7.25, 5.3, "λ Doc\nProcessor", fs=6.5)

box(8.3, 4.8, 1.7, 1.0, C_LAMBDA, "#E65100")
label(9.15, 5.3, "λ Req\nExtractor", fs=6.5)

box(10.2, 4.8, 1.7, 1.0, C_LAMBDA, "#E65100")
label(11.05, 5.3, "λ Expert\nMatcher", fs=6.5)

box(12.1, 4.8, 1.7, 1.0, C_LAMBDA, "#E65100")
label(12.95, 5.3, "λ Compliance\nChecker", fs=6.5)

# Shared layer
box(6.4, 4.2, 7.4, 0.45, "#BF360C", "#7F0000")
label(10.1, 4.42, "Lambda Layer  (boto3 · opensearch-py · cohere · langchain)", fs=6.5)

# ═══════════════════════════════════════════════════════════════════════════════
# 7. RAG PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════
dashed_box(14.5, 4.0, 10.8, 9.0, ec="#6C3483", label="Advanced RAG Pipeline", fc="#F5EEF8", lw=1.8)

# Hybrid Search
box(14.7, 10.8, 3.0, 1.8, C_RAG, "#4A235A")
label(16.2, 11.7, "Hybrid Search Engine", fs=7.5, bold=True)
label(16.2, 11.25, "Vector (kNN) + BM25 Full-Text", fs=6.5, color="#E8DAEF")
label(16.2, 10.95, "Reciprocal Rank Fusion (RRF)", fs=6.5, color="#E8DAEF")

# HyDE
box(14.7, 9.5, 1.4, 1.0, "#7D3C98", "#4A235A")
label(15.4, 10.0, "HyDE\nEmbeddings", fs=6.5)

# Query Decomposition
box(16.3, 9.5, 1.6, 1.0, "#7D3C98", "#4A235A")
label(17.1, 10.0, "Query\nDecomposition", fs=6.5)

# CRAG
box(18.1, 9.5, 1.5, 1.0, "#7D3C98", "#4A235A")
label(18.85, 10.0, "Corrective\nRAG (CRAG)", fs=6.5)

# Self-Reflective RAG
box(19.8, 9.5, 1.6, 1.0, "#7D3C98", "#4A235A")
label(20.6, 10.0, "Self-Reflect\nRAG (SRAG)", fs=6.5)

# Reranking
box(21.6, 9.5, 2.5, 1.0, "#7D3C98", "#4A235A")
label(22.85, 10.0, "Re-ranking\n(Cohere + LLM fallback)", fs=6.5)

# Semantic Cache
box(14.7, 8.2, 2.2, 1.0, C_REDIS, "#7B241C")
label(15.8, 8.7, "Semantic Cache\n(ElastiCache Redis)", fs=6.5)

# Knowledge Graph
box(17.1, 8.2, 3.2, 1.0, C_KG, "#784212")
label(18.7, 8.7, "Knowledge Graph\n(Comprehend NER + Neptune)", fs=6.5)

# Grounded Citations
box(20.5, 8.2, 3.6, 1.0, "#1A5276", "#0E3460")
label(22.3, 8.7, "Grounded Citations\n+ Hallucination Detection", fs=6.5)

# Adaptive Router
box(14.7, 7.0, 9.4, 0.9, "#512E5F", "#2C1654")
label(19.4, 7.45, "Adaptive Query Router  (vector_only | text_only | hybrid | decomposed)", fs=6.8)

# Titan Embeddings
box(14.7, 5.8, 2.8, 0.9, C_BEDROCK, "#00695C")
label(16.1, 6.25, "Titan Embed\nText v2", fs=6.5)

# Bedrock Models
box(17.7, 5.8, 3.2, 0.9, C_BEDROCK, "#00695C")
label(19.3, 6.25, "Bedrock Models\nClaude 3.5 Sonnet / Haiku", fs=6.5)

# Textract + Comprehend
box(21.1, 5.8, 4.0, 0.9, C_TEXTRACT, "#00695C")
label(23.1, 6.25, "Textract (OCR)\n+ Comprehend (NER)", fs=6.5)

# Guardrails
box(14.7, 4.8, 2.8, 0.7, "#B7950B", "#7D6608")
label(16.1, 5.15, "Bedrock Guardrails", fs=6.5)

# Cohere Secret
box(17.7, 4.8, 2.4, 0.7, "#1B4F72", "#0E2F44")
label(18.9, 5.15, "Secrets Manager\n(Cohere API Key)", fs=6.5)

# ═══════════════════════════════════════════════════════════════════════════════
# 8. DATA STORES
# ═══════════════════════════════════════════════════════════════════════════════
dashed_box(6.2, 0.6, 18.0, 3.2, ec="#1B5E20", label="Data Stores", fc="#F1F8E9")

# S3
box(6.4, 1.4, 2.4, 1.2, C_S3, "#1B5E20")
label(7.6, 2.0, "Amazon S3\nDocument Bucket\n(Versioned · SSL)", fs=6.5)

# Aurora PostgreSQL
box(9.2, 1.4, 3.0, 1.2, C_RDS, "#0D47A1")
label(10.7, 2.0, "Aurora PostgreSQL\nServerless v2 + pgvector\n(requirements_db)", fs=6.5)

# OpenSearch Serverless
box(12.5, 1.4, 3.0, 1.2, C_OS, "#4A148C")
label(14.0, 2.0, "OpenSearch\nServerless\n(Vector + BM25 index)", fs=6.5)

# ElastiCache Redis
box(15.8, 1.4, 2.8, 1.2, C_REDIS, "#7B241C")
label(17.2, 2.0, "ElastiCache\nRedis 7.0\n(Semantic Cache)", fs=6.5)

# Neptune
box(18.9, 1.4, 2.8, 1.2, C_NEPTUNE, "#145A32")
label(20.3, 2.0, "Amazon Neptune\nKnowledge Graph\n(Gremlin)", fs=6.5)

# KG tables in Aurora
box(22.0, 1.4, 2.0, 1.2, "#5D4037", "#3E2723")
label(23.0, 2.0, "Aurora KG\nTables\n(kg_nodes/edges)", fs=6.5)

# ═══════════════════════════════════════════════════════════════════════════════
# 9. OBSERVABILITY (top-right)
# ═══════════════════════════════════════════════════════════════════════════════
dashed_box(20.5, 14.0, 5.0, 3.2, ec="#FF4F8B", label="Observability", fc="#FFF0F5")

box(20.7, 15.8, 2.0, 1.1, C_CW, "#880E4F")
label(21.7, 16.35, "CloudWatch\nMetrics & Logs", fs=6.5)

box(23.0, 15.8, 2.2, 1.1, "#FF6F00", "#E65100")
label(24.1, 16.35, "X-Ray\nDistributed\nTracing", fs=6.5)

box(20.7, 14.5, 4.5, 1.0, "#37474F", "#263238")
label(22.95, 15.0, "API Gateway Metrics · Lambda Insights · RDS Performance", fs=6.2)

# ═══════════════════════════════════════════════════════════════════════════════
# 10. VPC boundary note
# ═══════════════════════════════════════════════════════════════════════════════
dashed_box(6.2, 3.8, 13.8, 9.8, ec="#546E7A", label="VPC  (Public / Private / Isolated subnets · NAT Gateway)", fc="none", lw=1.2)

# ═══════════════════════════════════════════════════════════════════════════════
# ARROWS — data flows
# ═══════════════════════════════════════════════════════════════════════════════

# User <-> React
darrow(1.9, 9.05, 2.4, 9.9, "HTTP/WS", "#1565C0", lbl_offset=(0, 0.15))

# React <-> FastAPI
arrow(3.8, 9.8, 3.8, 9.3, "REST / SSE", "#009688", lbl_offset=(0.5, 0))

# FastAPI -> Cognito (auth)
arrow(3.0, 8.2, 3.0, 7.8, "Authenticate", C_COGNITO, lbl_offset=(0.6, 0))

# FastAPI -> API Gateway
arrow(5.2, 8.75, 6.2, 9.0, "invoke_agent\n+ REST calls", "#6A0DAD", lbl_offset=(0, 0.15))

# API Gateway -> Bedrock Agent
arrow(8.6, 9.0, 9.0, 10.0, "InvokeAgent\n(SSE)", C_AGENT, lbl_offset=(0.1, 0.1))

# API Gateway -> Lambda (direct REST)
arrow(7.4, 8.5, 9.15, 5.8, "Direct\nLambda", C_LAMBDA, lbl_offset=(0.3, 0.1))

# Bedrock Agent -> Lambda action groups
arrow(11.6, 7.2, 11.05, 5.8, "Action\nGroups", C_LAMBDA, lbl_offset=(0.4, 0))

# Lambda -> S3
arrow(7.25, 4.8, 7.6, 2.6, "GetObject\nPutObject", C_S3, lbl_offset=(0.5, 0))

# Lambda -> Aurora
arrow(9.15, 4.8, 10.7, 2.6, "RDS Data API\n(SQL)", C_RDS, lbl_offset=(0.3, 0.1))

# Lambda -> OpenSearch
arrow(11.05, 4.8, 14.0, 2.6, "kNN + BM25\nSearch", C_OS, lbl_offset=(0.2, 0.1))

# Lambda -> RAG Pipeline
arrow(13.9, 5.3, 14.7, 10.0, "search(query)", C_RAG, lbl_offset=(0.4, 0))

# RAG -> OpenSearch
arrow(16.2, 10.8, 14.0, 2.6, "Vector + Text\nQueries", C_OS, lbl_offset=(-0.5, 0.1))

# RAG -> Titan Embeddings
arrow(16.2, 10.8, 16.1, 6.7, "embed_text()", C_BEDROCK, lbl_offset=(0.5, 0))

# RAG -> Bedrock Models (CRAG / SRAG)
arrow(18.85, 9.5, 19.3, 6.7, "invoke_model()", C_BEDROCK, lbl_offset=(0.5, 0))

# RAG -> Semantic Cache
arrow(16.2, 10.8, 15.8, 9.2, "cache.get/set", C_REDIS, lbl_offset=(0.5, 0))

# RAG -> Knowledge Graph
arrow(16.2, 10.8, 18.7, 9.2, "enrich_results\n_with_graph()", C_KG, lbl_offset=(0, 0.15))

# KG -> Neptune
arrow(18.7, 8.2, 20.3, 2.6, "Gremlin\nTraversal", C_NEPTUNE, lbl_offset=(0.4, 0.1))

# KG -> Comprehend
arrow(18.7, 8.2, 23.1, 6.7, "detect_entities()", C_COMPREH, lbl_offset=(0, 0.15))

# Semantic Cache -> Redis
arrow(15.8, 8.2, 17.2, 2.6, "GET/SET", C_REDIS, lbl_offset=(0.4, 0))

# Bedrock Agent -> Knowledge Bases
arrow(11.6, 7.4, 14.0, 2.6, "Retrieve\n(KB)", C_BEDROCK, lbl_offset=(-0.3, 0.1))

# S3 -> Textract
arrow(7.6, 2.6, 23.1, 5.8, "StartDocumentText\nDetection", C_TEXTRACT, lbl_offset=(0, 0.15))

# Lambda -> Guardrails
arrow(12.95, 4.8, 16.1, 5.5, "Apply\nGuardrails", "#B7950B", lbl_offset=(0, 0.15))

# Observability arrows
arrow(11.6, 12.6, 21.7, 15.8, "Traces / Metrics", C_CW, lbl_offset=(0, 0.15))
arrow(9.15, 5.8, 24.1, 15.8, "X-Ray Traces", "#FF6F00", lbl_offset=(0, 0.15))

# Aurora KG tables
arrow(10.7, 2.6, 23.0, 2.0, "kg_nodes\nkg_edges", "#5D4037", lbl_offset=(0, 0.15))

# ═══════════════════════════════════════════════════════════════════════════════
# TITLE
# ═══════════════════════════════════════════════════════════════════════════════
ax.text(13.0, 17.7,
        "Requirements Management AI — Full Architecture",
        fontsize=14, fontweight="bold", color="#1A237E",
        ha="center", va="center", zorder=6)
ax.text(13.0, 17.3,
        "UI · FastAPI · API Gateway · Bedrock Agent (AgentCore) · Lambda · Advanced RAG · Knowledge Graph · Data Stores · Observability",
        fontsize=7.5, color="#455A64", ha="center", va="center", zorder=6)

# ═══════════════════════════════════════════════════════════════════════════════
# LEGEND
# ═══════════════════════════════════════════════════════════════════════════════
legend_items = [
    (C_AGENT,   "Bedrock Agent"),
    (C_LAMBDA,  "Lambda"),
    (C_RAG,     "RAG Pipeline"),
    (C_KG,      "Knowledge Graph"),
    (C_RDS,     "Aurora PostgreSQL"),
    (C_OS,      "OpenSearch"),
    (C_REDIS,   "ElastiCache Redis"),
    (C_NEPTUNE, "Neptune"),
    (C_S3,      "S3"),
    (C_CW,      "Observability"),
]
for i, (color, lbl) in enumerate(legend_items):
    bx = 0.3 + (i % 5) * 2.8
    by = 0.3 if i >= 5 else 1.1
    ax.add_patch(mpatches.Rectangle((bx, by), 0.35, 0.28, color=color, zorder=6))
    ax.text(bx + 0.45, by + 0.14, lbl, fontsize=6.2, va="center", color="#263238", zorder=6)

out = "architecture_diagram.png"
plt.tight_layout(pad=0.2)
plt.savefig(out, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"Saved: {out}")
