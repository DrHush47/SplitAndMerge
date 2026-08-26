const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun,
  LevelFormat, AlignmentType, LineRuleType,
} = require('docx');

const FONT = 'Times New Roman';
const SIZE = 28; // half-points => 14pt

const children = Array.from({ length: 15 }, (_, i) =>
  new Paragraph({
    numbering: { reference: 'hello-list', level: 0 },
    spacing: {
      line: 240,
      lineRule: LineRuleType.AUTO,
      before: 0,
      after: 0,
    },
    children: [
      new TextRun({ text: 'Привет', font: FONT, size: SIZE }),
      ...(i === 14 ? [] : []),
    ],
  })
);

const doc = new Document({
  styles: {
    default: {
      document: {
        run: { font: FONT, size: SIZE },
        paragraph: { spacing: { line: 240, lineRule: LineRuleType.AUTO } },
      },
    },
  },
  numbering: {
    config: [
      {
        reference: 'hello-list',
        levels: [
          {
            level: 0,
            format: LevelFormat.DECIMAL,
            text: '%1.',
            alignment: AlignmentType.START,
            style: {
              paragraph: {
                indent: { left: 720, hanging: 360 },
                spacing: { line: 240, lineRule: LineRuleType.AUTO, before: 0, after: 0 },
              },
              run: { font: FONT, size: SIZE },
            },
          },
        ],
      },
    ],
  },
  sections: [{ properties: {}, children }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync('привет.docx', buf);
  console.log('OK: привет.docx written,', children.length, 'items');
});
