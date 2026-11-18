package com.lawwiz.business.review;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

import com.lawwiz.business.api.ApiError;
import org.apache.poi.xwpf.usermodel.XWPFDocument;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/** Check document order and the failures exposed to contract review tasks. */
class ContractTextTest {
    @Test
    void retainsDocxParagraphAndTableOrder() throws Exception {
        try (var document = new XWPFDocument(); var output = new ByteArrayOutputStream()) {
            document.createParagraph().createRun().setText("合同正文");
            var table = document.createTable(1, 2);
            table.getRow(0).getCell(0).setText("交付");
            table.getRow(0).getCell(1).setText("验收");
            document.createParagraph().createRun().setText("付款");
            document.write(output);
            var extracted = ContractText.extract(output.toByteArray(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document");
            assertThat(extracted.text()).isEqualTo("合同正文\n交付\t验收\n付款");
        }
    }

    @Test
    void removesUtf8BomAndRejectsScannedFile() {
        assertThat(ContractText.extract("\uFEFF合同".getBytes(StandardCharsets.UTF_8), "text/plain").text())
                .isEqualTo("合同");
        assertThatThrownBy(() -> ContractText.extract(new byte[8], "image/png"))
                .isInstanceOf(ApiError.class).hasMessageContaining("OCR");
    }
}
