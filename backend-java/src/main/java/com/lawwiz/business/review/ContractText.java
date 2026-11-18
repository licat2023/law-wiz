package com.lawwiz.business.review;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.stream.Collectors;
import java.util.zip.ZipInputStream;

import com.lawwiz.business.api.ApiError;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.encryption.InvalidPasswordException;
import org.apache.pdfbox.text.PDFTextStripper;
import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.apache.poi.xwpf.usermodel.XWPFParagraph;
import org.apache.poi.xwpf.usermodel.XWPFTable;
import org.apache.poi.xwpf.usermodel.XWPFTableCell;

/** Extract PDF, DOCX and TXT in reading order with bounded document expansion. */
final class ContractText {
    private static final int MAX_TEXT = 2_000_000;
    private static final int MAX_PDF_PAGES = 300;
    private static final int MAX_PDF_PAGE_BYTES = 16 * 1024 * 1024;
    private static final int MAX_WORD_BYTES = 64 * 1024 * 1024;
    record Extracted(String text, Integer pages) {}

    private ContractText() {}

    static Extracted extract(byte[] bytes, String mime) {
        try {
            var result = switch (mime == null ? "" : mime) {
                case "application/pdf" -> pdf(bytes);
                case "application/vnd.openxmlformats-officedocument.wordprocessingml.document" -> word(bytes);
                case "text/plain", "text/plain; charset=utf-8" -> new Extracted(readText(bytes), null);
                default -> throw failure("当前版本暂不支持扫描件 OCR，请上传含正文的文件。");
            };
            if (result.text().isBlank()) {
                throw failure("未提取到正文，请上传含正文的 PDF、DOCX 或 TXT 文件。");
            }
            checkLength(result.text());
            return result;
        } catch (ApiError error) {
            throw error;
        } catch (InvalidPasswordException error) {
            throw failure("请先解除 PDF 密码保护。");
        } catch (IOException | RuntimeException error) {
            throw failure("文件无法解析，请检查格式、编码或文件是否损坏。");
        }
    }

    private static String readText(byte[] bytes) throws IOException {
        var text = StandardCharsets.UTF_8.newDecoder().decode(ByteBuffer.wrap(bytes)).toString();
        return text.startsWith("\uFEFF") ? text.substring(1) : text;
    }

    private static Extracted pdf(byte[] data) throws IOException {
        try (var document = Loader.loadPDF(new org.apache.pdfbox.io.RandomAccessReadBuffer(data),
                org.apache.pdfbox.io.IOUtils.createTempFileOnlyStreamCache())) {
            if (document.isEncrypted()) {
                throw failure("请先解除 PDF 密码保护。");
            }
            int count = document.getNumberOfPages();
            if (count > MAX_PDF_PAGES) {
                throw failure("PDF 页数超过处理上限。");
            }
            StringBuilder body = new StringBuilder();
            var stripper = new PDFTextStripper();
            stripper.setLineSeparator("\n");
            for (int page = 1; page <= count; page++) {
                try (var contents = document.getPage(page - 1).getContents()) {
                    if (contents != null) {
                        contents.transferTo(new BoundedOutput(MAX_PDF_PAGE_BYTES, "PDF 单页内容超过处理上限。"));
                    }
                }
                stripper.setStartPage(page);
                stripper.setEndPage(page);
                if (page > 1) {
                    body.append('\n');
                }
                body.append(stripper.getText(document).stripTrailing());
                checkLength(body);
            }
            return new Extracted(body.toString(), count);
        }
    }

    private static Extracted word(byte[] data) throws IOException {
        try (var zip = new ZipInputStream(new ByteArrayInputStream(data))) {
            var sink = new BoundedOutput(MAX_WORD_BYTES, "Word 解压后大小超过处理上限。");
            while (zip.getNextEntry() != null) {
                zip.transferTo(sink);
            }
        }
        try (var document = new XWPFDocument(new ByteArrayInputStream(data))) {
            StringBuilder body = new StringBuilder();
            for (var element : document.getBodyElements()) {
                String text = switch (element) {
                    case XWPFParagraph paragraph -> paragraph.getText();
                    case XWPFTable table -> table.getRows().stream()
                            .map(row -> row.getTableCells().stream().map(XWPFTableCell::getText)
                                    .collect(Collectors.joining("\t")))
                            .collect(Collectors.joining("\n"));
                    default -> "";
                };
                if (!text.isBlank()) {
                    if (!body.isEmpty()) {
                        body.append('\n');
                    }
                    body.append(text);
                    checkLength(body);
                }
            }
            return new Extracted(body.toString(), null);
        }
    }

    private static void checkLength(CharSequence text) {
        if (text.length() > MAX_TEXT && Character.codePointCount(text, 0, text.length()) > MAX_TEXT) {
            throw failure("解析文本超过长度上限。");
        }
    }

    private static ApiError failure(String message) {
        return new ApiError(40907, message);
    }

    private static final class BoundedOutput extends java.io.OutputStream {
        private long remaining;
        private final String message;

        BoundedOutput(long max, String message) {
            remaining = max;
            this.message = message;
        }

        @Override
        public void write(int value) {
            write(null, 0, 1);
        }

        @Override
        public void write(byte[] bytes, int offset, int length) {
            remaining -= length;
            if (remaining < 0) {
                throw failure(message);
            }
        }
    }
}
