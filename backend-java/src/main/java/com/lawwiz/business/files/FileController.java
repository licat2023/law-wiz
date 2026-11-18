package com.lawwiz.business.files;

import java.math.BigInteger;

import com.lawwiz.business.api.ApiEnvelope;
import com.lawwiz.business.api.ApiValues;
import com.lawwiz.business.api.RateLimits;
import com.lawwiz.business.auth.AccessTokens;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

/** Expose compatible multipart upload and protected file metadata. */
@RestController
@RequestMapping("/api/files")
class FileController {
    private final BusinessFiles files;
    private final AccessTokens tokens;
    private final RateLimits limits;
    private final int readLimit;

    FileController(BusinessFiles files, AccessTokens tokens, RateLimits limits,
                   @Value("${LAWWIZ_RATE_LIMIT_READ_PER_MINUTE:120}") int readLimit) {
        this.files = files;
        this.tokens = tokens;
        this.limits = limits;
        this.readLimit = readLimit;
    }

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    ApiEnvelope upload(@RequestParam MultipartFile file, HttpServletRequest request, HttpServletResponse response) {
        return ApiEnvelope.success(files.upload(user(request, response), file), request);
    }

    @GetMapping("/{id}")
    ApiEnvelope metadata(@PathVariable String id, HttpServletRequest request, HttpServletResponse response) {
        return ApiEnvelope.success(files.metadata(user(request, response), ApiValues.id(id)), request);
    }

    private BigInteger user(HttpServletRequest request, HttpServletResponse response) {
        BigInteger id = tokens.requireUser(request.getHeader("Authorization"));
        limits.require("read", id.toString(), readLimit, response);
        return id;
    }
}
