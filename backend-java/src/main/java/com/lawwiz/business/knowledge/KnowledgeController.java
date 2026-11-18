package com.lawwiz.business.knowledge;

import java.math.BigInteger;
import java.time.LocalDate;

import com.lawwiz.business.api.ApiEnvelope;
import com.lawwiz.business.api.RateLimits;
import com.lawwiz.business.api.RequestIds;
import com.lawwiz.business.auth.AccessTokens;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

/** Preserve the public knowledge API while the separate knowledge service owns its records. */
@RestController
@RequestMapping("/api/knowledge_base")
class KnowledgeController {
    record Document(@NotNull @Pattern(regexp = "law|interpretation|case|template") String docType,
                    @Min(1) @Max(3) Integer corpusTier,
                    @NotNull @Size(min = 1, max = 300) String title, @Size(max = 200) String lawName,
                    @Size(max = 64) String articleNo, @Size(max = 300) String chapterPath,
                    LocalDate effectiveDate, LocalDate abolishedDate,
                    @Size(max = 32) String revision, @Size(max = 200) String source,
                    @Size(max = 512) String sourceUrl, @NotNull @Size(min = 1, max = 500000) String content) {}
    record Index(Boolean force) {}

    private final KnowledgeService knowledge;
    private final AccessTokens tokens;
    private final RateLimits limits;
    private final int readLimit;
    private final int aiLimit;

    KnowledgeController(KnowledgeService knowledge, AccessTokens tokens, RateLimits limits,
                        @Value("${LAWWIZ_RATE_LIMIT_READ_PER_MINUTE:120}") int readLimit,
                        @Value("${LAWWIZ_RATE_LIMIT_AI_PER_MINUTE:10}") int aiLimit) {
        this.knowledge = knowledge;
        this.tokens = tokens;
        this.limits = limits;
        this.readLimit = readLimit;
        this.aiLimit = aiLimit;
    }

    @PostMapping("/documents")
    @ResponseStatus(HttpStatus.CREATED)
    ApiEnvelope create(@Valid @RequestBody Document payload, HttpServletRequest request, HttpServletResponse response) {
        var owner = authorize(request, response, "read", readLimit);
        return ApiEnvelope.success(knowledge.create(owner, RequestIds.get(request), payload), request);
    }

    @PostMapping("/documents/{id}/index")
    @ResponseStatus(HttpStatus.ACCEPTED)
    ApiEnvelope index(@PathVariable String id, @RequestBody(required = false) Index payload,
                      HttpServletRequest request, HttpServletResponse response) {
        var owner = authorize(request, response, "ai", aiLimit);
        return ApiEnvelope.success(knowledge.index(owner, RequestIds.get(request), id,
                payload != null && Boolean.TRUE.equals(payload.force())), request);
    }

    @GetMapping("/documents")
    ApiEnvelope list(@RequestParam(defaultValue = "1") int page,
                     @RequestParam(name = "page_size", defaultValue = "20") int size,
                     @RequestParam(name = "doc_type", required = false) String type,
                     @RequestParam(name = "corpus_tier", required = false) Integer tier,
                     @RequestParam(name = "index_status", required = false) String status,
                     @RequestParam(name = "law_name", required = false) String law,
                     @RequestParam(defaultValue = "-created_at") String sort,
                     HttpServletRequest request, HttpServletResponse response) {
        authorize(request, response, "read", readLimit);
        return ApiEnvelope.success(knowledge.list(RequestIds.get(request), page, size, type, tier, status, law, sort),
                request);
    }

    @GetMapping("/documents/{id}")
    ApiEnvelope detail(@PathVariable String id, HttpServletRequest request, HttpServletResponse response) {
        authorize(request, response, "read", readLimit);
        return ApiEnvelope.success(knowledge.detail(RequestIds.get(request), id), request);
    }

    @GetMapping("/search")
    ApiEnvelope search(@RequestParam String q, @RequestParam(name = "top_k", defaultValue = "5") int limit,
                       @RequestParam(name = "doc_type", required = false) String type,
                       @RequestParam(name = "corpus_tier", required = false) Integer tier,
                       @RequestParam(name = "include_abolished", defaultValue = "false") boolean includeAbolished,
                       HttpServletRequest request, HttpServletResponse response) {
        authorize(request, response, "read", readLimit);
        return ApiEnvelope.success(knowledge.search(RequestIds.get(request), q, limit, type, tier, includeAbolished),
                request);
    }

    private BigInteger authorize(HttpServletRequest request, HttpServletResponse response, String category, int limit) {
        BigInteger user = tokens.requireUser(request.getHeader("Authorization"));
        limits.require(category, user.toString(), limit, response);
        return user;
    }
}
