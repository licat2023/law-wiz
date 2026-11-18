package com.lawwiz.business.qa;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/** Map sessions, messages, and citation snapshots in the existing MySQL schema. */
@Mapper
interface QaMapper {
    String SESSIONS = "id,user_id,review_task_id,risk_point_id,title,status,message_count,last_message_at,created_at";
    String MESSAGES = "id,qa_session_id,`role`,content,has_citation,model_name,latency_ms,created_at";

    record Session(BigInteger id, BigInteger userId, BigInteger reviewTaskId, BigInteger riskPointId,
                   String title, String status, int messageCount, LocalDateTime lastMessageAt, LocalDateTime createdAt) {}
    record Message(BigInteger id, BigInteger qaSessionId, String role, String content, boolean hasCitation,
                   String modelName, Integer latencyMs, LocalDateTime createdAt) {}
    record Turn(String role, String content) {}
    record Citation(BigInteger qaMessageId, String documentId, String chunkId, String quotedText,
                    String sourceSnapshot, BigDecimal relevanceScore) {}

    @Select("SELECT " + SESSIONS + " FROM qa_session WHERE id = #{id} AND deleted_at IS NULL")
    Session find(BigInteger id);

    @Update("""
            UPDATE qa_session SET review_task_id = NULL, risk_point_id = NULL,
                updated_at = CURRENT_TIMESTAMP(3) WHERE review_task_id = #{task}
            """)
    void detachReview(BigInteger task);

    @Select("SELECT " + SESSIONS + " FROM qa_session WHERE id = #{id} AND deleted_at IS NULL FOR UPDATE")
    Session lock(BigInteger id);

    @Insert("INSERT INTO qa_session(user_id,review_task_id,risk_point_id,title) VALUES(#{userId},#{taskId},#{riskId},#{title})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    void create(Map<String, Object> data);

    @Select("""
            SELECT COUNT(*) FROM qa_session WHERE user_id = #{owner} AND deleted_at IS NULL
            AND (#{status} IS NULL OR status = #{status})
            """)
    long countSessions(BigInteger owner, String status);

    @Select("SELECT " + SESSIONS + """
             FROM qa_session WHERE user_id = #{owner} AND deleted_at IS NULL
             AND (#{status} IS NULL OR status = #{status})
             ORDER BY
                 CASE WHEN #{sort} = '-last_message_at' THEN last_message_at END DESC,
                 CASE WHEN #{sort} = 'last_message_at' THEN last_message_at END ASC,
                 CASE WHEN #{sort} = '-created_at' THEN created_at END DESC,
                 CASE WHEN #{sort} = 'created_at' THEN created_at END ASC, id ASC
             LIMIT #{size} OFFSET #{offset}
            """)
    List<Session> list(BigInteger owner, String status, String sort, int size, long offset);

    @Select("SELECT COUNT(*) FROM qa_message WHERE qa_session_id = #{id}")
    long countMessages(BigInteger id);

    @Select("SELECT " + MESSAGES + " FROM qa_message WHERE qa_session_id = #{id} ORDER BY id LIMIT #{size} OFFSET #{offset}")
    List<Message> messages(BigInteger id, int size, long offset);

    @Select("SELECT id FROM qa_message WHERE qa_session_id = #{session} AND id = #{id} AND `role` = 'assistant'")
    BigInteger assistantMessage(BigInteger session, BigInteger id);

    @Select("""
            <script>
            SELECT qa_message_id,
                   COALESCE(NULLIF(external_document_id,''), CAST(knowledge_base_document_id AS CHAR)) AS document_id,
                   COALESCE(NULLIF(external_chunk_id,''), CAST(knowledge_base_chunk_id AS CHAR)) AS chunk_id,
                   quoted_text, source_snapshot, relevance_score
            FROM qa_citation WHERE qa_message_id IN
                <foreach collection="ids" item="id" open="(" separator="," close=")">#{id}</foreach>
            ORDER BY id
            </script>
            """)
    List<Citation> citations(@Param("ids") List<BigInteger> ids);

    @Insert("INSERT INTO qa_message(qa_session_id,`role`,content) VALUES(#{sessionId},#{role},#{content})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    void createMessage(Map<String, Object> data);

    @Update("""
            UPDATE qa_session SET title = COALESCE(NULLIF(title,''), #{title}), message_count = message_count + 2,
                last_message_at = CURRENT_TIMESTAMP(3), updated_at = CURRENT_TIMESTAMP(3)
            WHERE id = #{id}
            """)
    void countTurn(BigInteger id, String title);

    @Update("UPDATE qa_session SET status = 'archived', updated_at = CURRENT_TIMESTAMP(3) WHERE id = #{id}")
    void archive(BigInteger id);

    @Select("""
            SELECT `role`, SUBSTRING(content,1,600) AS content FROM qa_message
            WHERE qa_session_id = #{session} AND id < #{before}
              AND (`role` = 'user' OR (`role` = 'assistant' AND latency_ms IS NOT NULL))
            ORDER BY id DESC LIMIT 6
            """)
    List<Turn> recent(BigInteger session, BigInteger before);

    @Update("""
            UPDATE qa_message SET content = #{content}, has_citation = #{hasCitation},
                model_name = #{model}, latency_ms = #{latency}
            WHERE id = #{id} AND `role` = 'assistant' AND content = ''
            """)
    int finish(BigInteger id, String content, boolean hasCitation, String model, Integer latency);

    @Insert("""
            INSERT INTO qa_citation(qa_message_id, external_service, external_knowledge_base_id,
                external_document_id, external_chunk_id, external_revision_id, external_index_id, quoted_text,
                relevance_score, source_snapshot)
            VALUES(#{id},'knowledge_base',#{base},#{document},#{chunk},#{revision},#{index},#{text},#{score},#{snapshot})
            """)
    void cite(BigInteger id, String base, String document, String chunk, String revision,
              String index, String text, BigDecimal score, String snapshot);
}
