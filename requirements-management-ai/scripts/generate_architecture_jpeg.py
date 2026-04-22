from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

W, H = 2600, 1500
BG = (245, 246, 248)

img = Image.new("RGB", (W, H), BG)
draw = ImageDraw.Draw(img)

try:
    font_title = ImageFont.truetype("arial.ttf", 30)
    font_section = ImageFont.truetype("arial.ttf", 22)
    font_box = ImageFont.truetype("arial.ttf", 18)
except Exception:
    font_title = ImageFont.load_default()
    font_section = ImageFont.load_default()
    font_box = ImageFont.load_default()


def box(x1, y1, x2, y2, text, fill=(255, 255, 255), outline=(70, 70, 70), width=3):
    draw.rounded_rectangle([x1, y1, x2, y2], radius=12, fill=fill, outline=outline, width=width)
    tw = draw.multiline_textbbox((0, 0), text, font=font_box, spacing=4)
    text_w = tw[2] - tw[0]
    text_h = tw[3] - tw[1]
    tx = x1 + (x2 - x1 - text_w) / 2
    ty = y1 + (y2 - y1 - text_h) / 2
    draw.multiline_text((tx, ty), text, font=font_box, fill=(20, 20, 20), align="center", spacing=4)


def section(x1, y1, x2, y2, title, outline=(130, 130, 130)):
    draw.rounded_rectangle([x1, y1, x2, y2], radius=14, outline=outline, width=3)
    draw.rectangle([x1 + 12, y1 - 18, x1 + 340, y1 + 18], fill=BG)
    draw.text((x1 + 18, y1 - 14), title, font=font_section, fill=(40, 40, 40))


def arrow(x1, y1, x2, y2, label=None, color=(90, 90, 90), width=3):
    draw.line([x1, y1, x2, y2], fill=color, width=width)
    import math

    angle = math.atan2(y2 - y1, x2 - x1)
    alen = 14
    a1 = angle + 2.6
    a2 = angle - 2.6
    p1 = (x2 + alen * math.cos(a1), y2 + alen * math.sin(a1))
    p2 = (x2 + alen * math.cos(a2), y2 + alen * math.sin(a2))
    draw.polygon([(x2, y2), p1, p2], fill=color)

    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        lb = draw.textbbox((0, 0), label, font=font_box)
        lw = lb[2] - lb[0]
        lh = lb[3] - lb[1]
        pad = 4
        draw.rectangle([mx - lw / 2 - pad, my - lh / 2 - pad, mx + lw / 2 + pad, my + lh / 2 + pad], fill=BG)
        draw.text((mx - lw / 2, my - lh / 2), label, font=font_box, fill=(50, 50, 50))


# Title
main_title = "Requirements Management AI - Code-Derived Architecture"
tb = draw.textbbox((0, 0), main_title, font=font_title)
draw.text(((W - (tb[2] - tb[0])) / 2, 20), main_title, font=font_title, fill=(15, 15, 15))

# Global sections
section(40, 110, 430, 580, "Client Zone")
section(470, 110, 2520, 1360, "AWS Account (CDK + Runtime)")
section(1650, 120, 2490, 430, "Observability")
section(520, 520, 1570, 1280, "Bedrock Agent Runtime + Action Groups")
section(1610, 520, 2460, 1280, "Data & Knowledge Layer")

# Client components
box(80, 190, 230, 270, "Users", fill=(255, 255, 255))
box(250, 170, 400, 290, "React Frontend\n(Vite + Axios + SSE)", fill=(226, 240, 255), outline=(47, 117, 181))
box(120, 340, 380, 500, "FastAPI Backend\n`backend/main.py`\n\nRoutes:\n- /api/agent/invoke\n- /api/documents\n- /api/requirements\n- /api/experts\n- /api/compliance", fill=(230, 245, 235), outline=(74, 140, 94))

# Runtime/API
box(560, 180, 830, 310, "API Gateway\n(REST API /v1)", fill=(255, 240, 220), outline=(199, 130, 36))
box(860, 180, 1220, 340, "Bedrock Agent\nRequirementsManagementAgent\nClaude 3.5 Sonnet", fill=(239, 229, 255), outline=(128, 75, 176))
box(1240, 180, 1610, 340, "Knowledge Bases (3)\n- requirements-index\n- regulatory-index\n- experts-index\n(Titan Embed v2)", fill=(233, 242, 255), outline=(58, 106, 180))

# Action groups
box(580, 600, 910, 760, "Lambda: DocumentProcessor\nTextract + Comprehend\nChunking + registry update", fill=(255, 248, 227), outline=(170, 128, 30))
box(950, 600, 1280, 760, "Lambda: RequirementsExtractor\nBedrock extraction\nStructured requirements", fill=(255, 248, 227), outline=(170, 128, 30))
box(1320, 600, 1650, 760, "Lambda: ExpertMatcher\nEmbedding similarity\nExpert assignment", fill=(255, 248, 227), outline=(170, 128, 30))
box(760, 830, 1120, 1020, "Lambda: ComplianceChecker\nHybrid RAG + CRAG\nGrounded citations", fill=(255, 248, 227), outline=(170, 128, 30))
box(1150, 830, 1540, 1020, "Hybrid Search Engine\n`src/rag/hybrid_search.py`\nvector + text + RRF + rerank\nHyDE + decomposition + cache", fill=(237, 255, 243), outline=(69, 146, 89))

# Data layer
box(1660, 600, 1960, 760, "Amazon S3\nDocument Bucket\n`bids/*`", fill=(255, 239, 230), outline=(191, 103, 52))
box(1990, 600, 2380, 790, "Aurora PostgreSQL\nServerless v2 + Data API\nTables: requirements, experts,\nkg_nodes, kg_edges, registry", fill=(231, 246, 255), outline=(46, 129, 181))
box(1660, 860, 1960, 1020, "OpenSearch Serverless\nVector + BM25", fill=(237, 233, 255), outline=(108, 84, 170))
box(1990, 860, 2380, 1020, "Redis (ElastiCache)\nSemantic Cache", fill=(255, 231, 231), outline=(180, 68, 68))
box(1660, 1080, 1960, 1240, "Amazon Bedrock\nRuntime + Embeddings", fill=(224, 255, 249), outline=(26, 139, 126))
box(1990, 1080, 2380, 1240, "Secrets Manager\nCohere API key\nDB secrets", fill=(250, 250, 220), outline=(144, 144, 40))

# Observability
box(1690, 180, 1960, 320, "CloudWatch Logs\nAPI Gateway + Lambda", fill=(248, 239, 255), outline=(138, 84, 171))
box(2000, 180, 2230, 320, "AWS X-Ray\nTracing enabled", fill=(248, 239, 255), outline=(138, 84, 171))
box(2260, 180, 2450, 320, "Langfuse\n(optional)", fill=(250, 250, 250), outline=(120, 120, 120))

# Arrows - client flow
arrow(230, 230, 250, 230)
arrow(400, 230, 560, 240, "HTTPS")
arrow(400, 380, 560, 260, "REST")
arrow(380, 420, 860, 260, "SSE /agent/invoke")

# Arrows - API/Agent
arrow(830, 245, 860, 245)
arrow(1220, 260, 1240, 260)
arrow(1030, 340, 760, 600, "Invoke action")
arrow(1030, 340, 1110, 600, "Invoke action")
arrow(1030, 340, 1470, 600, "Invoke action")
arrow(1030, 340, 940, 830, "Invoke action")

# Arrows - data interactions
arrow(910, 680, 1660, 680, "Read/Write docs")
arrow(1110, 680, 1990, 680, "Store requirements")
arrow(1470, 680, 1990, 730, "Read experts")
arrow(1120, 920, 1660, 940, "Retrieve")
arrow(1540, 920, 1660, 940)
arrow(1540, 920, 1990, 940, "Cache")
arrow(1540, 930, 1660, 1140, "Invoke model")
arrow(1540, 950, 1990, 1160, "Secrets")
arrow(1240, 300, 1720, 900, "KB retrieval")
arrow(1240, 290, 1720, 1140, "Titan embeddings")

# Observability links
arrow(760, 580, 1820, 320, "Logs")
arrow(1110, 580, 2110, 320, "Traces")
arrow(940, 830, 2360, 320, "optional traces")

# Footer
footer = "Generated from current repository architecture (frontend, backend, CDK, RAG modules)."
fb = draw.textbbox((0, 0), footer, font=font_box)
draw.text(((W - (fb[2] - fb[0])) / 2, H - 40), footer, font=font_box, fill=(70, 70, 70))

out_path = Path(__file__).resolve().parents[1] / "docs" / "architecture_from_code.jpeg"
out_path.parent.mkdir(parents=True, exist_ok=True)
img.save(out_path, format="JPEG", quality=95)

print(str(out_path))
