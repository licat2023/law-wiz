package com.lawwiz.business.review;

import java.math.BigInteger;
import java.nio.charset.StandardCharsets;

import com.lawwiz.business.api.ApiEnvelope;
import com.lawwiz.business.api.ApiError;
import com.lawwiz.business.api.ApiValues;
import com.lawwiz.business.api.Idempotency;
import com.lawwiz.business.api.RateLimits;
import com.lawwiz.business.api.RequestIds;
import com.lawwiz.business.auth.AccessTokens;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** Serve existing submission, polling, report and risk review endpoints. */
@RestController
@RequestMapping("/api/reviews")
class ReviewController {
    record Create(@NotNull @Size(max = 32) String fileId, @Size(max = 200) String contractTitle, Boolean force) {}
    record Dismiss(@NotNull Boolean isDismissed) {}

    private final ReviewService reviews;
    private final AccessTokens tokens;
    private final Idempotency idempotency;
    private final RateLimits limits;
    private final int readLimit;
    private final int pollLimit;
    private final int aiLimit;

    ReviewController(ReviewService reviews, AccessTokens tokens, Idempotency idempotency, RateLimits limits,
                     @Value("${LAWWIZ_RATE_LIMIT_READ_PER_MINUTE:120}") int readLimit,
                     @Value("${LAWWIZ_RATE_LIMIT_POLL_PER_MINUTE:60}") int pollLimit,
                     @Value("${LAWWIZ_RATE_LIMIT_AI_PER_MINUTE:10}") int aiLimit) {
        this.reviews = reviews;
        this.tokens = tokens;
        this.idempotency = idempotency;
        this.limits = limits;
        this.readLimit = readLimit;
        this.pollLimit = pollLimit;
        this.aiLimit = aiLimit;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.ACCEPTED)
    ApiEnvelope create(@Valid @RequestBody Create payload, HttpServletRequest request, HttpServletResponse response) {
        var owner = authorize(request, response, "ai", aiLimit);
        var data = idempotency.submit("review:" + owner, request.getHeader("Idempotency-Key"),
                () -> reviews.create(owner, ApiValues.id(payload.fileId()), payload.contractTitle(), Boolean.TRUE.equals(payload.force()),
                        RequestIds.get(request)));
        return ApiEnvelope.success(data, request);
    }

    @GetMapping
    ApiEnvelope list(@RequestParam(defaultValue = "1") int page,
                     @RequestParam(name = "page_size", defaultValue = "20") int size,
                     @RequestParam(required = false) String status,
                     @RequestParam(defaultValue = "-created_at") String sort,
                     HttpServletRequest request, HttpServletResponse response) {
        return ApiEnvelope.success(reviews.list(authorize(request, response, "read", readLimit), status, sort, page, size),
                request);
    }

    @GetMapping("/{id}")
    ApiEnvelope status(@PathVariable String id, HttpServletRequest request, HttpServletResponse response) {
        return ApiEnvelope.success(reviews.status(authorize(request, response, "poll", pollLimit), ApiValues.id(id)),
                request);
    }

    @GetMapping("/{id}/result")
    ApiEnvelope result(@PathVariable String id, HttpServletRequest request, HttpServletResponse response) {
        return ApiEnvelope.success(reviews.result(authorize(request, response, "read", readLimit), ApiValues.id(id)),
                request);
    }

    @GetMapping("/{id}/report")
    ResponseEntity<byte[]> download(@PathVariable String id, @RequestParam(defaultValue = "pdf") String format,
                                    HttpServletRequest request, HttpServletResponse response) {
        if (!"pdf".equals(format)) {
            throw new ApiError(40001, "format 取值不合法");
        }
        var report = reviews.download(authorize(request, response, "read", readLimit), ApiValues.id(id));
        var name = report.filename().replaceAll("[\\p{Cntrl}]", "");
        return ResponseEntity.ok().contentType(MediaType.APPLICATION_PDF)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment().filename(name, StandardCharsets.UTF_8).build().toString())
                .body(report.bytes());
    }

    @PatchMapping("/{id}/risk-points/{pointId}")
    ApiEnvelope dismiss(@PathVariable String id, @PathVariable String pointId, @Valid @RequestBody Dismiss payload,
                        HttpServletRequest request, HttpServletResponse response) {
        return ApiEnvelope.success(reviews.dismiss(authorize(request, response, "read", readLimit), ApiValues.id(id),
                ApiValues.id(pointId), payload.isDismissed()), request);
    }

    private BigInteger authorize(HttpServletRequest request, HttpServletResponse response, String category, int limit) {
        BigInteger user = tokens.requireUser(request.getHeader("Authorization"));
        limits.require(category, user.toString(), limit, response);
        return user;
    }
}
