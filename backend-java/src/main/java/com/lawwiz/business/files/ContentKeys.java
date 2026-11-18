package com.lawwiz.business.files;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.regex.Pattern;

/** Compute object keys compatible with files written by the Python backend. */
public final class ContentKeys {
    private static final Pattern DIGEST = Pattern.compile("[a-f0-9]{64}");
    private ContentKeys() {}

    public static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
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
