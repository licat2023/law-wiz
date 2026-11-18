package com.lawwiz.business.files;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.DigestInputStream;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.regex.Pattern;

/** Compute object keys compatible with files written by the Python backend. */
public final class ContentKeys {
    private static final Pattern DIGEST = Pattern.compile("[a-f0-9]{64}");
    private ContentKeys() {}

    public static String sha256(byte[] bytes) {
        return HexFormat.of().formatHex(newDigest().digest(bytes));
    }

    /** Compute the digest of a staged upload without buffering the full file. */
    static String sha256(Path path) throws IOException {
        var digest = newDigest();
        try (var contents = new DigestInputStream(Files.newInputStream(path), digest)) {
            contents.transferTo(OutputStream.nullOutputStream());
        }
        return HexFormat.of().formatHex(digest.digest());
    }

    private static MessageDigest newDigest() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }

    public static String key(String digest) {
        if (!DIGEST.matcher(digest).matches()) {
            throw new IllegalArgumentException("Expected a SHA-256 digest");
        }
        return "files/" + digest.substring(0, 2) + "/" + digest;
    }
}
