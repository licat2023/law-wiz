package com.lawwiz.business.api;

import java.math.BigInteger;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.regex.Pattern;

/** Convert MySQL unsigned IDs and Shanghai timestamps at the business boundary. */
public final class ApiValues {
    private static final BigInteger MAX_ID = new BigInteger("18446744073709551615");
    private static final ZoneOffset SHANGHAI_OFFSET = ZoneOffset.ofHours(8);
    private static final Pattern ID = Pattern.compile("[1-9][0-9]{0,19}");

    private ApiValues() {}

    public static BigInteger id(String value) {
        if (value == null || !ID.matcher(value).matches()) {
            throw new ApiError(40001, "ID 格式不合法");
        }
        BigInteger parsed = new BigInteger(value);
        if (parsed.compareTo(MAX_ID) > 0) {
            throw new ApiError(40001, "ID 超出范围");
        }
        return parsed;
    }

    public static String timestamp(LocalDateTime value) {
        return value == null ? null : value.atOffset(SHANGHAI_OFFSET).format(DateTimeFormatter.ISO_OFFSET_DATE_TIME);
    }

    public static String limit(String value, int maxCodePoints) {
        if (value == null || value.codePointCount(0, value.length()) <= maxCodePoints) {
            return value;
        }
        return value.substring(0, value.offsetByCodePoints(0, maxCodePoints));
    }

    public static long offset(int page, int size) {
        if (page < 1 || size < 1 || size > 100) {
            throw new ApiError(40003, "分页参数超出范围（page_size 上限 100）");
        }
        return (page - 1L) * size;
    }
}
