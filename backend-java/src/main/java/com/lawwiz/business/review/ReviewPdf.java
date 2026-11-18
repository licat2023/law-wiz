package com.lawwiz.business.review;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.file.Path;
import java.util.List;

import com.lawwiz.business.api.ApiError;
import org.apache.fontbox.ttf.TrueTypeCollection;
import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.common.PDRectangle;
import org.apache.pdfbox.pdmodel.font.PDType0Font;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;

/** Render printable reports with an embedded Chinese font. */
@Component
class ReviewPdf {
    private final Path fontPath;

    ReviewPdf(@Value("${LAWWIZ_REPORT_FONT:/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc}") Path fontPath) {
        this.fontPath = fontPath;
    }

    byte[] render(String title, String summary, JsonNode terms, List<JsonNode> risks) {
        try (var document = new PDDocument();
             var font = new ReportFont(fontPath);
             var output = new ByteArrayOutputStream()) {
            try (var page = new Writing(document, font.load(document))) {
                page.line("智法宝 · 合同审查报告", 19);
                page.line("合同：" + title, 13);
                page.line(summary, 12);
                page.line("合同条款", 14);
                terms.properties().forEach(entry -> page.bodyLine(termLabel(entry.getKey()) + "：" + entry.getValue()));
                page.line("风险明细", 14);
                int number = 0;
                for (var risk : risks) {
                    page.line(++number + ". " + risk.path("clause_title").asString("未命名条款"), 13);
                    page.line("级别：" + riskLabel(risk.path("risk_level").asString("")), 11);
                    String excerpt = risk.path("clause_text").asString("");
                    page.line("合同原文：" + (excerpt.isBlank() ? "未定位到可核对的原文" : excerpt), 11);
                    page.line("风险：" + risk.path("description").asString(""), 11);
                    writeIfPresent(page, "修改建议：", risk.path("suggestion").asString(""));
                    writeIfPresent(page, "依据：", risk.path("legal_basis").asString(""));
                }
                page.line("本报告供参考，请结合合同原文及实际情况核对。", 10);
            }
            document.save(output);
            return output.toByteArray();
        } catch (IOException | java.io.UncheckedIOException error) {
            throw new ApiError(50000, "审查报告生成失败");
        }
    }

    private void writeIfPresent(Writing page, String label, String value) throws IOException {
        if (!value.isBlank()) {
            page.line(label + value, 11);
        }
    }

    private String riskLabel(String risk) {
        return switch (risk) {
            case "high" -> "高";
            case "low" -> "低";
            default -> "中";
        };
    }

    private String termLabel(String key) {
        return switch (key) {
            case "parties" -> "当事方";
            case "amount" -> "金额";
            case "payment_terms" -> "付款条款";
            case "liability" -> "违约责任";
            case "jurisdiction" -> "争议解决";
            case "term" -> "合同期限";
            default -> key;
        };
    }

    private static final class ReportFont implements AutoCloseable {
        private final Path path;
        private final TrueTypeCollection collection;

        ReportFont(Path path) throws IOException {
            this.path = path;
            collection = path.toString().toLowerCase(java.util.Locale.ROOT).endsWith(".ttc")
                    ? new TrueTypeCollection(path.toFile()) : null;
        }

        PDType0Font load(PDDocument document) throws IOException {
            if (collection == null) {
                return PDType0Font.load(document, path.toFile());
            }
            org.apache.fontbox.ttf.TrueTypeFont[] candidate = new org.apache.fontbox.ttf.TrueTypeFont[1];
            collection.processAllFonts(font -> {
                if (candidate[0] == null) {
                    candidate[0] = font;
                }
            });
            if (candidate[0] == null) {
                throw new IOException("No TrueType font in " + path);
            }
            return PDType0Font.load(document, candidate[0], true);
        }

        @Override
        public void close() throws IOException {
            if (collection != null) {
                collection.close();
            }
        }
    }

    private static final class Writing implements AutoCloseable {
        private final PDDocument document;
        private final PDType0Font font;
        private PDPageContentStream stream;
        private float height;

        Writing(PDDocument document, PDType0Font font) {
            this.document = document;
            this.font = font;
        }

        void bodyLine(String value) {
            try {
                line(value, 11);
            } catch (IOException error) {
                throw new java.io.UncheckedIOException(error);
            }
        }

        void line(String value, int size) throws IOException {
            for (String paragraph : value.split("\\R", -1)) {
                StringBuilder row = new StringBuilder();
                float width = 0;
                for (int offset = 0; offset < paragraph.length();) {
                    int codePoint = paragraph.codePointAt(offset);
                    offset += Character.charCount(codePoint);
                    String token = glyph(codePoint);
                    float advance = font.getStringWidth(token) * size / 1000;
                    if (width + advance > 490 && !row.isEmpty()) {
                        draw(row.toString(), size);
                        row.setLength(0);
                        width = 0;
                    }
                    row.append(token);
                    width += advance;
                }
                draw(row.toString(), size);
            }
            height -= 3;
        }

        private String glyph(int codePoint) throws IOException {
            if (Character.isISOControl(codePoint)) {
                return " ";
            }
            String token = Character.toString(codePoint);
            try {
                font.encode(token);
                return token;
            } catch (IllegalArgumentException unsupported) {
                return "□";
            }
        }

        private void draw(String text, int size) throws IOException {
            if (stream == null || height < 55) {
                close();
                var page = new PDPage(PDRectangle.A4);
                document.addPage(page);
                stream = new PDPageContentStream(document, page);
                height = page.getMediaBox().getHeight() - 56;
            }
            stream.beginText();
            stream.setFont(font, size);
            stream.newLineAtOffset(52, height);
            stream.showText(text);
            stream.endText();
            height -= size + 5;
        }

        @Override
        public void close() throws IOException {
            if (stream != null) {
                stream.close();
                stream = null;
            }
        }
    }
}
