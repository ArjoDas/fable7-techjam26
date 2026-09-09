from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor, Color
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output/pdf/Fable7-TechJam-Poster.pdf'
pdfmetrics.registerFont(TTFont('Arial',r'C:\Windows\Fonts\arial.ttf'))
pdfmetrics.registerFont(TTFont('Arial-Bold',r'C:\Windows\Fonts\arialbd.ttf'))
W,H=1190.55,1683.78
c=canvas.Canvas(str(OUT),pagesize=(W,H))
c.setTitle('Fable7 | Evidence-first Conversational Search | TikTok TechJam 2026')
c.setAuthor('Arjo Das, Mok Jun Wen, Srivathsan Ram')
NAVY='#142D3B'; INK='#203A49'; MUTED='#506572'; CYAN='#00A9AF'; PINK='#E94970'; PALE='#EAF7F7'; BLUE='#EDF3F7'; LINE='#CDDDE4'; WHITE='#FFFFFF'
def rect(x,y,w,h,fill,stroke=None,r=12):
    c.setFillColor(HexColor(fill)); c.setStrokeColor(HexColor(stroke or fill)); c.setLineWidth(1)
    c.roundRect(x,H-y-h,w,h,r,fill=1,stroke=bool(stroke))
def text(x,y,s,size=20,bold=False,color=INK,align='left'):
    c.setFillColor(HexColor(color)); c.setFont('Arial-Bold' if bold else 'Arial',size)
    {'left':c.drawString,'center':c.drawCentredString,'right':c.drawRightString}[align](x,H-y-size,s)
def para(x,y,w,s,size=18,leading=None,color=INK,bold=False):
    sty=ParagraphStyle('p',fontName='Arial-Bold' if bold else 'Arial',fontSize=size,leading=leading or size*1.3,textColor=HexColor(color),spaceAfter=0)
    p=Paragraph(s,sty); _,h=p.wrap(w,1000); p.drawOn(c,x,H-y-h); return h
def line(points,color=CYAN,width=2.5,dash=False,arrow=True):
    c.setStrokeColor(HexColor(color)); c.setFillColor(HexColor(color)); c.setLineWidth(width); c.setDash(5,4) if dash else c.setDash()
    p=c.beginPath(); p.moveTo(points[0][0],H-points[0][1])
    for x,y in points[1:]:p.lineTo(x,H-y)
    c.drawPath(p); c.setDash()
    if arrow:
        import math
        (x0,y0),(x,y)=points[-2:]; a=math.atan2(y-y0,x-x0); d=8
        p=c.beginPath(); p.moveTo(x,H-y)
        p.lineTo(x-d*math.cos(a-.48),H-(y-d*math.sin(a-.48)))
        p.lineTo(x-d*math.cos(a+.48),H-(y-d*math.sin(a+.48))); p.close();c.drawPath(p,fill=1,stroke=0)
def section(y,n,title,subtitle=None):
    rect(48,y+3,29,29,CYAN,r=7);text(62.5,y+7,n,15,True,WHITE,'center')
    text(90,y,title,27,True,NAVY)
    if subtitle:text(1142,y+8,subtitle,15,False,MUTED,'right')
def node(x,y,w,h,num,title,body,fill=BLUE,size=18):
    rect(x,y,w,h,fill,LINE)
    rect(x+15,y+15,29,29,NAVY,r=8);text(x+29.5,y+19,str(num),15,True,WHITE,'center')
    text(x+56,y+16,title,21,True,NAVY)
    para(x+18,y+49,w-36,body,size,size*1.15)

# Header: official event identity / project / supplied team logo.
rect(0,0,W,H,WHITE,r=0)
rect(0,0,W,10,NAVY,r=0)
c.drawImage(str(ROOT/'tmp/pdfs/techjam-official.jpg'),48,H-98,width=322,height=43,preserveAspectRatio=True,anchor='c')
text(48,105,'CONVERSATIONAL SEARCH TRACK',13,True,MUTED)
text(W/2,30,'FABLE 7',68,True,NAVY,'center')
text(W/2,109,'Arjo Das  /  Mok Jun Wen  /  Srivathsan Ram',15,False,MUTED,'center')
c.drawImage(r'C:\Users\sri56\AppData\Local\Temp\codex-clipboard-3d7cc0a4-4fef-486b-a78c-e740892f9a26.jpg',964,H-130,width=174,height=116,preserveAspectRatio=True,anchor='c')
text(W/2,149,'Find the right product. Know when to ask.',31,True,NAVY,'center')

# A conceptual funnel: numerical caps are code-grounded, not invented sample counts.
rect(48,204,1094,132,NAVY,r=16)
funnel=[(72,275,'50,000','catalog products'),(399,273,'Up to 80','retrieval candidates'),(720,178,'Matching set','ordered clues'),(944,162,'1 target','when evidence is unique')]
for i,(x,w,big,small) in enumerate(funnel):
    text(x+w/2,229,big,34 if i<2 else 25,True,WHITE,'center')
    text(x+w/2,280,small,16,False,'#D5E9ED','center')
    if i<3:line([(x+w+5,259),(x+w+32,259)],'#29D5D0',3)
text(595,314,'Clues narrow the evidence set across turns; prefix matches can enter from the full catalog.',13,False,'#D5E9ED','center')

section(363,'01','How the agent works','Exact architecture  /  Read top to bottom')
rect(68,408,1054,42,PALE,r=8)
text(85,420,'BUILT ONCE FROM THE CATALOG',13,True,CYAN)
text(372,419,'SQLite FTS5  +  exact-value index  +  ordered evidence-card prefix index',17,False,INK)
node(68,471,1054,83,1,'Remember the conversation','Accumulate clues and category. On intent override: remove stale opening preferences, keep later clues, reset shown items.',size=18)
line([(595,554),(595,566),(318,566),(318,578)])
line([(595,566),(864,566),(864,578)])
node(68,578,504,121,'2A','Lexical retrieval','Category-scoped BM25: AND terms, adjacent phrases, OR terms.<br/>Weighted reciprocal-rank fusion (RRF) retains up to 60.',size=18)
node(618,578,504,121,'2B','Exact-evidence lookup','Match normalized catalog attributes and fragments.<br/>Use material / color aliases; take up to 60 exact candidates.',size=18)
line([(318,699),(318,724)])
line([(870,699),(870,709),(554,709),(554,724)])
node(68,724,504,119,3,'Merge + learned reranking','Prioritize exact hits; deduplicate the union (cap: 80).<br/>A 16-feature linear model ranks the pool using JSON weights.',size=18)
line([(573,782),(617,782)])
node(618,724,504,119,4,'Match the ordered evidence prefix','For compatible dialogue, match category + ordered clues.<br/>Promote matches from the full catalog; break ties by popularity.',fill=PALE,size=18)
line([(870,843),(870,857),(318,857),(318,880)])
node(68,880,504,119,5,'Rotate candidates + choose output','If the query is unchanged, prefer items not shown before.<br/>Ambiguous or boundary case before turn 10? Return one.<br/>Otherwise, release the ranked list (up to 10).',size=17)
line([(573,935),(601,935),(601,906),(618,906)])
line([(601,935),(601,968),(618,968)])
rect(618,880,504,53,PALE,LINE,r=9)
text(638,889,'1 candidate + ask for the next requirement',20,True,NAVY)
text(638,916,'More evidence arrives on the next customer turn.',12,False,MUTED)
rect(618,947,504,52,NAVY,r=9)
text(870,960,'Return ranked recommendations: up to 10',20,True,WHITE,'center')
# Visible conversational loop; its label is deliberately outside the nodes.
line([(1122,906),(1155,906),(1155,512),(1123,512)],CYAN,2,dash=True)
c.saveState();c.translate(1171,H-773);c.rotate(90);c.setFont('Arial-Bold',13);c.setFillColor(HexColor(CYAN));c.drawString(0,0,'NEXT CUSTOMER REPLY');c.restoreState()
text(68,1009,'Fallbacks: unknown / empty category search → global search; incompatible or unmatched prefix → keep learned ranking.',13,False,MUTED)
text(68,1029,'Opening-turn policy may also return one candidate. Questions request the next requirement; no LLM selects an attribute.',13,False,MUTED)

section(1070,'02','Three breakthroughs')
cols=[48,421,794];cw=348
breaks=[('01','Index the evidence','A tuple of category + ordered clues becomes a direct prefix lookup, revealing which products remain indistinguishable.','Fast catalog-derived lookup'),('02','Abstain from extra guesses','Return one best candidate while evidence is ambiguous, then ask again instead of filling all 10 slots.','MRR ~0.85 → ~0.95'),('03','Rotate what was shown','When the query stays unchanged, try unseen candidates instead of repeating the same product.','MRR ~0.95 → 1.00')]
for x,(n,title,body,metric) in zip(cols,breaks):
    rect(x,1120,cw,162,BLUE,r=12)
    text(x+18,1136,n,15,True,CYAN);text(x+52,1131,title,22,True,NAVY)
    para(x+18,1170,cw-36,body,17,22)
    text(x+18,1254,metric,18,True,PINK)

section(1310,'03','Results','200 public sessions  /  Reported evaluation & ablations')
metrics=[('100%','targets found at rank 1'),('1.00','mean reciprocal rank'),('2.10','average turns to target'),('0.978','TechnicalScore')]
for x,(n,label) in zip([48,326,604,882],metrics):
    rect(x,1357,260,88,PALE,r=10);text(x+130,1364,n,36,True,NAVY,'center');text(x+130,1411,label,15,False,MUTED,'center')
text(48,1461,'BM25: 0.107',18,True,MUTED)
rect(229,1460,310,22,BLUE,r=5);rect(229,1460,33.17,22,MUTED,r=5)
text(620,1461,'Fable7: 0.978',18,True,NAVY)
rect(832,1460,310,22,PALE,r=5);rect(832,1460,303.18,22,CYAN,r=5)
text(595,1499,'~45 s / 200 sessions on laptop CPU     •     $0.00 inference     •     Zero tokens, APIs or GPU',18,True,NAVY,'center')

# Relevance and next steps form a final practical takeaway.
text(48,1543,'REAL-WORLD CONNECTION',17,True,CYAN)
para(48,1571,509,'Shopping assistants can remember corrections, ask before guessing, and run locally with predictable cost.',17,22)
text(620,1543,'FUTURE WORK',17,True,CYAN)
para(620,1571,430,'Test paraphrases, incomplete clues and new catalogs beyond the current exact-quote simulator.',17,22)
# Footnote and project QR.
text(48,1634,'Python standard library + SQLite FTS5  •  23 regression tests  •  5,000+ synthetic sessions with disjoint targets',12,False,MUTED)
text(48,1653,'Data: Amazon Reviews 2023, McAuley Lab, UCSD  |  Project: devpost.com/software/fable7',12,False,MUTED)
qr=QrCodeWidget('https://devpost.com/software/fable7'); b=qr.getBounds(); d=Drawing(68,68,transform=[68/(b[2]-b[0]),0,0,68/(b[3]-b[1]),0,0]);d.add(qr);renderPDF.draw(d,c,1076,H-1632)
text(1110,1634,'PROJECT',10,True,NAVY,'center')
c.linkURL('https://devpost.com/software/fable7',(1076,H-1632,1144,H-1564),relative=0)
c.showPage();c.save()
print(OUT)
