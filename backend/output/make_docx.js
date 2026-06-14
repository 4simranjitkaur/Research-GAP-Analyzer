const {
  Document, Packer, Paragraph, TextRun, HeadingLevel,
  AlignmentType, LevelFormat, BorderStyle
} = require('docx');
const fs = require('fs');
const path = require('path');
const os = require('os');

const inputPath = path.join(os.tmpdir(), 'docx_input.json');
const outputPath = path.join(os.tmpdir(), 'output.docx');
const data = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
const { topic, content, docType, date } = data;

// Parse markdown content into paragraphs
function parseContent(text) {
  const lines = text.split('\n');
  const paragraphs = [];

  const bulletConfig = {
    reference: "bullets",
    levels: [{
      level: 0,
      format: LevelFormat.BULLET,
      text: "\u2022",
      alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 720, hanging: 360 } } }
    }]
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      paragraphs.push(new Paragraph({ children: [new TextRun("")], spacing: { after: 80 } }));
      continue;
    }

    // H1
    const h1 = trimmed.match(/^#\s+(.*)/);
    if (h1) {
      paragraphs.push(new Paragraph({
        heading: HeadingLevel.HEADING_1,
        children: [new TextRun({ text: h1[1], bold: true, size: 32, font: "Arial" })],
        spacing: { before: 240, after: 120 }
      }));
      continue;
    }

    // H2
    const h2 = trimmed.match(/^##\s+(.*)/);
    if (h2) {
      paragraphs.push(new Paragraph({
        heading: HeadingLevel.HEADING_2,
        children: [new TextRun({ text: h2[1], bold: true, size: 28, font: "Arial" })],
        spacing: { before: 200, after: 100 }
      }));
      continue;
    }

    // H3
    const h3 = trimmed.match(/^###\s+(.*)/);
    if (h3) {
      paragraphs.push(new Paragraph({
        heading: HeadingLevel.HEADING_3,
        children: [new TextRun({ text: h3[1], bold: true, size: 24, font: "Arial" })],
        spacing: { before: 160, after: 80 }
      }));
      continue;
    }

    // Bullet
    const bullet = trimmed.match(/^[-*]\s+(.*)/);
    if (bullet) {
      const cleaned = bullet[1].replace(/\*\*(.*?)\*\*/g, '$1').replace(/\*(.*?)\*/g, '$1');
      paragraphs.push(new Paragraph({
        numbering: { reference: "bullets", level: 0 },
        children: [new TextRun({ text: cleaned, size: 22, font: "Arial" })],
        spacing: { after: 60 }
      }));
      continue;
    }

    // Table row (skip for now, render as text)
    if (trimmed.startsWith('|')) continue;

    // Normal paragraph — handle **bold**
    const parts = trimmed.split(/(\*\*.*?\*\*)/);
    const runs = parts.map(p => {
      if (p.startsWith('**') && p.endsWith('**')) {
        return new TextRun({ text: p.slice(2, -2), bold: true, size: 22, font: "Arial" });
      }
      return new TextRun({ text: p.replace(/\*(.*?)\*/g, '$1'), size: 22, font: "Arial" });
    });

    paragraphs.push(new Paragraph({
      children: runs,
      spacing: { after: 100 },
      alignment: AlignmentType.JUSTIFIED
    }));
  }

  return { paragraphs, bulletConfig };
}

const { paragraphs, bulletConfig } = parseContent(content);

const doc = new Document({
  numbering: { config: [bulletConfig] },
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      {
        id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: "1F3864" },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0 }
      },
      {
        id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: "2E5FA3" },
        paragraph: { spacing: { before: 200, after: 100 }, outlineLevel: 1 }
      },
      {
        id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: "4472C4" },
        paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 2 }
      },
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 }
      }
    },
    children: [
      // Title
      new Paragraph({
        children: [new TextRun({ text: docType, bold: true, size: 48, font: "Arial", color: "1F3864" })],
        alignment: AlignmentType.CENTER,
        spacing: { after: 120 }
      }),
      // Topic
      new Paragraph({
        children: [new TextRun({ text: `Topic: ${topic}`, size: 28, font: "Arial", color: "444444" })],
        alignment: AlignmentType.CENTER,
        spacing: { after: 80 }
      }),
      // Date
      new Paragraph({
        children: [new TextRun({ text: date, size: 20, font: "Arial", color: "888888" })],
        alignment: AlignmentType.CENTER,
        spacing: { after: 240 },
        border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "2E5FA3", space: 1 } }
      }),
      new Paragraph({ children: [new TextRun("")], spacing: { after: 200 } }),
      ...paragraphs
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync(outputPath, buffer);
  console.log('DOCX created successfully');
}).catch(err => {
  console.error('Error:', err);
  process.exit(1);
});
