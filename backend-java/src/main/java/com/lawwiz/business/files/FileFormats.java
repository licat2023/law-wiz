package com.lawwiz.business.files;

import java.io.BufferedInputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.zip.ZipException;
import java.util.zip.ZipFile;

import com.lawwiz.business.api.ApiError;

/** Identify supported uploads by their content rather than their supplied extension. */
public enum FileFormats {
    PDF("application/pdf"),
    DOCX("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    TXT("text/plain; charset=utf-8"),
    JPEG("image/jpeg"),
    PNG("image/png");

    private final String mimeType;

    FileFormats(String mimeType) {
        this.mimeType = mimeType;
    }

    public String mimeType() {
        return mimeType;
    }

    static FileFormats identify(Path file) throws IOException {
        byte[] signature;
        try (var bytes = Files.newInputStream(file)) {
            signature = bytes.readNBytes(8);
        }
        if (startsWith(signature, "%PDF-".getBytes(StandardCharsets.US_ASCII))) {
            return PDF;
        }
        if (startsWith(signature, new byte[]{(byte) 255, (byte) 216, (byte) 255})) {
            return JPEG;
        }
        if (startsWith(signature, new byte[]{(byte) 137, 80, 78, 71, 13, 10, 26, 10})) {
            return PNG;
        }
        if (startsWith(signature, new byte[]{80, 75, 3, 4}) && isDocx(file)) {
            return DOCX;
        }
        if (isText(file)) {
            return TXT;
        }
        throw new ApiError(41501, "仅支持可提取文本的 PDF、Word（.docx）、TXT 与 JPG/PNG 图片");
    }

    private static boolean startsWith(byte[] read, byte[] signature) {
        return read.length >= signature.length && Arrays.equals(
                read, 0, signature.length, signature, 0, signature.length);
    }

    private static boolean isDocx(Path file) throws IOException {
        try (var zip = new ZipFile(file.toFile())) {
            return zip.getEntry("[Content_Types].xml") != null
                    && zip.stream().anyMatch(entry -> entry.getName().startsWith("word/") && !entry.isDirectory());
        } catch (ZipException error) {
            return false;
        }
    }

    private static boolean isText(Path file) throws IOException {
        boolean nonWhitespace = false;
        try (var reader = new InputStreamReader(new BufferedInputStream(Files.newInputStream(file)),
                StandardCharsets.UTF_8.newDecoder())) {
            char[] buffer = new char[4096];
            int count;
            while ((count = reader.read(buffer)) != -1) {
                for (int index = 0; index < count; index++) {
                    char character = buffer[index];
                    if (character < 32 && character != '\t' && character != '\r' && character != '\n') {
                        return false;
                    }
                    nonWhitespace |= !Character.isWhitespace(character);
                }
            }
        } catch (CharacterCodingException error) {
            return false;
        }
        return nonWhitespace;
    }
}
