package com.lawwiz.business.review;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/** Maintain existing contract versions, task stages, and report snapshots. */
@Mapper
interface ReviewMapper {
    String TASK = "id,user_id,contract_id,contract_version_id,status,stage,progress,error_code,error_message,"
            + "started_at,finished_at,created_at,extracted_terms";
    String POINT = "id,risk_level,risk_category,clause_title,clause_text,char_start,char_end,"
            + "description,suggestion,legal_basis,source_type,confidence,is_dismissed";

    record Task(BigInteger id, BigInteger userId, BigInteger contractId, BigInteger contractVersionId,
                String status, String stage, int progress, String errorCode, String errorMessage,
                LocalDateTime startedAt, LocalDateTime finishedAt, LocalDateTime createdAt, String extractedTerms) {}
    record Version(BigInteger id, BigInteger contractId, BigInteger fileObjectId, String plainText) {}
    record Report(BigInteger fileObjectId, String summary, int highCount, int mediumCount, int lowCount) {}
    record Point(BigInteger id, String riskLevel, String riskCategory, String clauseTitle, String clauseText,
                 Integer charStart, Integer charEnd, String description, String suggestion, String legalBasis,
                 String sourceType, BigDecimal confidence, boolean isDismissed) {}
    record Rule(String riskLevel, String category, String conclusion, String suggestion, String legalBasis,
                String matchKeywords) {}

    @Select("SELECT id FROM user WHERE id = #{owner} FOR UPDATE")
    BigInteger lockOwner(BigInteger owner);

    @Select("""
            SELECT version.id,version.contract_id,version.file_object_id,version.plain_text
            FROM contract_version version JOIN contract ON contract.id = version.contract_id
            WHERE version.file_object_id = #{file} AND contract.owner_id = #{owner}
            ORDER BY version.id LIMIT 1
            """)
    Version findVersion(BigInteger owner, BigInteger file);

    @Select("SELECT id,contract_id,file_object_id,plain_text FROM contract_version WHERE id = #{id}")
    Version version(BigInteger id);

    @Insert("INSERT INTO contract(owner_id,title) VALUES(#{owner},#{title})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    void createContract(Map<String, Object> data);

    @Insert("INSERT INTO contract_version(contract_id,version_no,file_object_id,created_by) VALUES(#{contract},1,#{file},#{owner})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    void createVersion(Map<String, Object> data);

    @Update("UPDATE contract SET current_version_id = #{version} WHERE id = #{id}")
    void setVersion(BigInteger id, BigInteger version);

    @Update("UPDATE contract_version SET plain_text = #{text}, text_source = 'parse', page_count = #{pages} WHERE id = #{id}")
    void storeText(BigInteger id, String text, Integer pages);

    @Select("SELECT EXISTS(SELECT id FROM review_task WHERE contract_version_id = #{version} "
            + "AND status IN ('pending','processing') AND deleted_at IS NULL)")
    boolean hasRunningTask(BigInteger version);

    @Insert("INSERT INTO review_task(contract_id,contract_version_id,user_id) VALUES(#{contract},#{version},#{owner})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    void createTask(Map<String, Object> data);

    @Select("SELECT " + TASK + " FROM review_task WHERE id = #{id} AND deleted_at IS NULL")
    Task task(BigInteger id);

    @Select("SELECT title FROM contract WHERE id = #{id}")
    String contractTitle(BigInteger id);

    @Select("SELECT COUNT(*) FROM review_task WHERE user_id = #{owner} AND deleted_at IS NULL "
            + "AND (#{status} IS NULL OR status = #{status})")
    long count(BigInteger owner, String status);

    @Select("SELECT " + TASK + """
             FROM review_task WHERE user_id = #{owner} AND deleted_at IS NULL
             AND (#{status} IS NULL OR status = #{status})
             ORDER BY CASE WHEN #{sort} = '-created_at' THEN created_at END DESC,
                      CASE WHEN #{sort} = 'created_at' THEN created_at END ASC,
                      CASE WHEN #{sort} = '-finished_at' THEN finished_at END DESC,
                      CASE WHEN #{sort} = 'finished_at' THEN finished_at END ASC, id ASC
             LIMIT #{size} OFFSET #{offset}
            """)
    List<Task> list(BigInteger owner, String status, String sort, int size, long offset);

    @Update("""
            UPDATE review_task SET status = 'processing', stage = 'text_extract', progress = 15,
                started_at = CURRENT_TIMESTAMP(3), updated_at = CURRENT_TIMESTAMP(3),
                error_code = NULL, error_message = NULL
            WHERE id = #{id} AND status = 'pending' AND deleted_at IS NULL
            """)
    int begin(BigInteger id);

    @Update("UPDATE review_task SET stage = #{stage}, progress = #{progress}, updated_at = CURRENT_TIMESTAMP(3) WHERE id = #{id}")
    void stage(BigInteger id, String stage, int progress);

    @Update("""
            UPDATE review_task SET status = 'failed', error_code = #{code}, error_message = #{message},
                finished_at = CURRENT_TIMESTAMP(3), updated_at = CURRENT_TIMESTAMP(3)
            WHERE id = #{id} AND status IN ('pending','processing')
            """)
    void fail(BigInteger id, String code, String message);

    @Update("""
            UPDATE review_task SET status = 'succeeded', stage = NULL, progress = 100,
                extracted_terms = #{terms}, raw_llm_output = #{raw},
                finished_at = CURRENT_TIMESTAMP(3), updated_at = CURRENT_TIMESTAMP(3)
            WHERE id = #{id} AND status = 'processing'
            """)
    int finish(BigInteger id, String terms, String raw);

    @Select("SELECT risk_level,category,conclusion,suggestion,legal_basis,match_keywords "
            + "FROM risk_rule WHERE is_active = TRUE AND deleted_at IS NULL ORDER BY id")
    List<Rule> rules();

    @Select("SELECT " + POINT + " FROM risk_point WHERE review_task_id = #{id} AND deleted_at IS NULL ORDER BY id")
    List<Point> points(BigInteger id);

    @Select("SELECT " + POINT + " FROM risk_point WHERE review_task_id = #{taskId} AND id = #{pointId} AND deleted_at IS NULL")
    Point point(BigInteger taskId, BigInteger pointId);

    @Update("UPDATE risk_point SET is_dismissed = #{dismissed}, updated_at = CURRENT_TIMESTAMP(3) "
            + "WHERE review_task_id = #{taskId} AND id = #{pointId} AND deleted_at IS NULL")
    void dismiss(BigInteger taskId, BigInteger pointId, boolean dismissed);

    @Insert("""
            INSERT INTO risk_point(review_task_id,risk_level,risk_category,clause_title,clause_text,
                char_start,char_end,description,suggestion,legal_basis,source_type,confidence,source_snapshot,
                external_service,external_document_id,external_chunk_id,external_revision_id)
            VALUES(#{id},#{level},#{category},#{title},#{text},#{start},#{end},#{description},
                #{suggestion},#{basis},#{type},#{confidence},#{snapshot},#{service},#{document},#{chunk},#{revision})
            """)
    void insertPoint(Map<String, Object> data);

    @Select("SELECT file_object_id,summary,high_count,medium_count,low_count FROM review_report "
            + "WHERE review_task_id = #{id} AND deleted_at IS NULL")
    Report report(BigInteger id);

    @Insert("""
            INSERT INTO review_report(review_task_id,file_object_id,summary,high_count,medium_count,low_count)
            VALUES(#{id},#{file},#{summary},#{high},#{medium},#{low})
            """)
    void insertReport(BigInteger id, BigInteger file, String summary, int high, int medium, int low);
}
