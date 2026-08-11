<%@ WebHandler Language="C#" Class="DownloadPlanHandler" %>
using System;
using System.Collections.Generic;
using System.Configuration;
using System.Data;
using System.Data.SqlClient;
using System.IO;
using System.Web;
using System.Web.Script.Serialization;
public class DownloadPlanHandler : IHttpHandler
{
    private const int CommandTimeoutSeconds = 120;
    public void ProcessRequest(HttpContext context)
{
    JsonResponseHelper.Prepare(context);
    JavaScriptSerializer serializer =
        CreateSerializer();
    try
    {
        int planId;
        if (
            !TryReadPlanId(
                context,
                serializer,
                out planId
            )
        )
        {
            WriteJson(
                context,
                serializer,
                new ErrorResponse
                {
                    success = false,
                    message = "กรุณาระบุ plan_id ที่ถูกต้อง"
                },
                400
            );
            return;
        }
        string connectionString =
            ConfigurationManager.AppSettings["strConn"];
        if (String.IsNullOrWhiteSpace(connectionString))
        {
            throw new ConfigurationErrorsException(
                "ไม่พบ AppSettings key ชื่อ strConn"
            );
        }
        using (
            SqlConnection connection =
                new SqlConnection(connectionString)
        )
        {
            connection.Open();
            PlanDto plan =
                GetPlan(
                    connection,
                    planId
                );
            if (plan == null)
            {
                WriteJson(
                    context,
                    serializer,
                    new ErrorResponse
                    {
                        success = false,
                        message =
                            "ไม่พบ Plan ID " +
                            planId
                    },
                    404
                );
                return;
            }
            Dictionary<int, int> itemMap =
                BuildItemMap(
                    connection,
                    planId
                );
            List<ItemDto> items =
                GetMasterItems(
                    connection,
                    planId
                );
            List<BarcodeDto> barcodes =
                GetBarcodes(
                    connection,
                    planId
                );
            List<LocationDto> locations =
                GetLocations(
                    connection,
                    planId
                );
            List<PlanDetailDto> details =
                GetPlanDetails(
                    connection,
                    planId,
                    itemMap
                );
            DownloadResponse response =
                new DownloadResponse
                {
                    success = true,
                    message =
                        "Download plan สำเร็จ",
                    plan = plan,
                    items = items,
                    barcodes = barcodes,
                    locations = locations,
                    details = details,
                    summary =
                        new DownloadSummaryDto
                        {
                            item_count =
                                items.Count,
                            barcode_count =
                                barcodes.Count,
                            location_count =
                                locations.Count,
                            detail_count =
                                details.Count
                        }
                };
            WriteJson(
                context,
                serializer,
                response,
                200
            );
        }
    }
    catch (ConfigurationErrorsException ex)
    {
        WriteJson(
            context,
            serializer,
            new ErrorResponse
            {
                success = false,
                message =
                    "Server Configuration Error",
                error = ex.Message
            },
            500
        );
    }
    catch (SqlException ex)
    {
        WriteJson(
            context,
            serializer,
            new ErrorResponse
            {
                success = false,
                message = "Database Error",
                error = ex.Message
            },
            500
        );
    }
    catch (Exception ex)
    {
        WriteJson(
            context,
            serializer,
            new ErrorResponse
            {
                success = false,
                message = "Download Plan Error",
                error = ex.Message
            },
            500
        );
    }
}
    // =====================================================
    // Request
    // =====================================================
    private bool TryReadPlanId(
        HttpContext context,
        JavaScriptSerializer serializer,
        out int planId
    )
    {
        planId = 0;
        string value =
            context.Request.QueryString["plan_id"];
        if (String.IsNullOrWhiteSpace(value))
        {
            value = context.Request.Form["plan_id"];
        }
        if (
            !String.IsNullOrWhiteSpace(value) &&
            Int32.TryParse(value, out planId) &&
            planId > 0
        )
        {
            return true;
        }
        if (
            context.Request.InputStream != null &&
            context.Request.InputStream.CanRead
        )
        {
            context.Request.InputStream.Position = 0;
            using (StreamReader reader =
                new StreamReader(context.Request.InputStream))
            {
                string body = reader.ReadToEnd();
                if (!String.IsNullOrWhiteSpace(body))
                {
                    try
                    {
                        DownloadRequest request =
                            serializer.Deserialize<DownloadRequest>(
                                body
                            );
                        if (
                            request != null &&
                            request.plan_id > 0
                        )
                        {
                            planId = request.plan_id;
                            return true;
                        }
                    }
                    catch
                    {
                        // JSON ไม่ถูกต้อง ให้คืน false
                    }
                }
            }
        }
        return false;
    }
    // =====================================================
    // Plan
    // =====================================================
    private PlanDto GetPlan(
        SqlConnection connection,
        int planId
    )
    {
        const string sql = @"
SELECT
    plan_id,
    plan_code,
    plan_details,
    plan_check_date,
    plan_status,
    udf1,
    udf2,
    udf3,
    create_date,
    create_by,
    update_date,
    update_by,
    is_export
FROM tbt_plans
WHERE plan_status <> 'Close' and plan_id = @plan_id;
";
        using (SqlCommand command =
            new SqlCommand(sql, connection))
        {
            command.CommandTimeout =
                CommandTimeoutSeconds;
            command.Parameters.Add(
                "@plan_id",
                SqlDbType.Int
            ).Value = planId;
            using (SqlDataReader reader =
                command.ExecuteReader())
            {
                if (!reader.Read())
                {
                    return null;
                }
                return new PlanDto
                {
                    plan_id =
                        GetInt32(reader, "plan_id"),
                    plan_code =
                        GetString(reader, "plan_code"),
                    plan_details =
                        GetString(reader, "plan_details"),
                    plan_check_date =
                        GetNullableDateTime(
                            reader,
                            "plan_check_date"
                        ),
                    plan_status =
                        GetString(reader, "plan_status"),
                    udf1 =
                        GetString(reader, "udf1"),
                    udf2 =
                        GetString(reader, "udf2"),
                    udf3 =
                        GetString(reader, "udf3"),
                    create_date =
                        GetNullableDateTime(
                            reader,
                            "create_date"
                        ),
                    create_by =
                        GetNullableInt32(
                            reader,
                            "create_by"
                        ),
                    update_date =
                        GetNullableDateTime(
                            reader,
                            "update_date"
                        ),
                    update_by =
                        GetNullableInt32(
                            reader,
                            "update_by"
                        ),
                    is_export =
                        GetNullableInt32(
                            reader,
                            "is_export"
                        ) ?? 0
                };
            }
        }
    }
    // =====================================================
    // Item Mapping
    // =====================================================
    private Dictionary<int, int> BuildItemMap(
        SqlConnection connection,
        int planId
    )
    {
        const string sql = @"
;WITH RelevantItemCodes AS
(
    SELECT DISTINCT
        s.item_code
    FROM tbt_plan_details d
    INNER JOIN tbm_stock_item s
        ON s.item_id = d.item_id
    WHERE d.plan_id = @plan_id
),
MasterItems AS
(
    SELECT
        s.item_code,
        MIN(s.item_id) AS master_item_id
    FROM tbm_stock_item s
    INNER JOIN RelevantItemCodes r
        ON r.item_code = s.item_code
    GROUP BY
        s.item_code
)
SELECT
    s.item_id AS source_item_id,
    m.master_item_id
FROM tbm_stock_item s
INNER JOIN MasterItems m
    ON m.item_code = s.item_code;
";
        Dictionary<int, int> result =
            new Dictionary<int, int>();
        using (SqlCommand command =
            new SqlCommand(sql, connection))
        {
            command.CommandTimeout =
                CommandTimeoutSeconds;
            command.Parameters.Add(
                "@plan_id",
                SqlDbType.Int
            ).Value = planId;
            using (SqlDataReader reader =
                command.ExecuteReader())
            {
                while (reader.Read())
                {
                    int sourceItemId =
                        Convert.ToInt32(
                            reader["source_item_id"]
                        );
                    int masterItemId =
                        Convert.ToInt32(
                            reader["master_item_id"]
                        );
                    if (!result.ContainsKey(sourceItemId))
                    {
                        result.Add(
                            sourceItemId,
                            masterItemId
                        );
                    }
                }
            }
        }
        return result;
    }
    // =====================================================
    // Master Items
    // =====================================================
    private List<ItemDto> GetMasterItems(
        SqlConnection connection,
        int planId
    )
    {
        const string sql = @"
;WITH RelevantItemCodes AS
(
    SELECT DISTINCT
        s.item_code
    FROM tbt_plan_details d
    INNER JOIN tbm_stock_item s
        ON s.item_id = d.item_id
    WHERE d.plan_id = @plan_id
),
RankedItems AS
(
    SELECT
        s.item_id,
        s.item_code,
        s.item_name,
        s.category,
        s.unit_rate,
        s.qty,
        s.uom,
        s.unit_cost,
        s.batching_unit,
        s.batching_factor,
        s.is_active,
        ROW_NUMBER() OVER
        (
            PARTITION BY s.item_code
            ORDER BY
                CASE
                    WHEN ISNULL(s.is_active, 0) = 1
                        THEN 0
                    ELSE 1
                END,
                s.item_id
        ) AS row_no,
        MIN(s.item_id) OVER
        (
            PARTITION BY s.item_code
        ) AS master_item_id
    FROM tbm_stock_item s
    INNER JOIN RelevantItemCodes r
        ON r.item_code = s.item_code
)
SELECT
    master_item_id AS item_id,
    item_code,
    item_name,
    category,
    unit_rate,
    qty,
    uom,
    unit_cost,
    batching_unit,
    batching_factor,
    is_active
FROM RankedItems
WHERE row_no = 1
ORDER BY item_code;
";
        List<ItemDto> result =
            new List<ItemDto>();
        using (SqlCommand command =
            new SqlCommand(sql, connection))
        {
            command.CommandTimeout =
                CommandTimeoutSeconds;
            command.Parameters.Add(
                "@plan_id",
                SqlDbType.Int
            ).Value = planId;
            using (SqlDataReader reader =
                command.ExecuteReader())
            {
                while (reader.Read())
                {
                    result.Add(
                        new ItemDto
                        {
                            item_id =
                                GetInt32(
                                    reader,
                                    "item_id"
                                ),
                            item_code =
                                GetString(
                                    reader,
                                    "item_code"
                                ),
                            item_name =
                                GetString(
                                    reader,
                                    "item_name"
                                ),
                            category =
                                GetString(
                                    reader,
                                    "category"
                                ),
                            unit_rate =
                                GetDecimal(
                                    reader,
                                    "unit_rate"
                                ),
                            qty =
                                GetDecimal(
                                    reader,
                                    "qty"
                                ),
                            uom =
                                GetString(
                                    reader,
                                    "uom"
                                ),
                            unit_cost =
                                GetDecimal(
                                    reader,
                                    "unit_cost"
                                ),
                            batching_unit =
                                GetString(
                                    reader,
                                    "batching_unit"
                                ),
                            batching_factor =
                                GetDecimal(
                                    reader,
                                    "batching_factor"
                                ),
                            is_active =
                                GetNullableInt32(
                                    reader,
                                    "is_active"
                                ) ?? 0
                        }
                    );
                }
            }
        }
        return result;
    }
    // =====================================================
    // Barcodes
    // =====================================================
    private List<BarcodeDto> GetBarcodes(
        SqlConnection connection,
        int planId
    )
    {
        /*
         * นำ Barcode ทุกแถวของ item_code เดียวกัน
         * ไปผูกกับ MIN(item_id)
         *
         * UNION กับ item_code เพื่อให้ค้นหาด้วยรหัสสินค้าได้
         * แม้ใน tbm_stock_item จะยังไม่มีแถว barcode=item_code
         */
        const string sql = @"
;WITH RelevantItemCodes AS
(
    SELECT DISTINCT
        s.item_code
    FROM tbt_plan_details d
    INNER JOIN tbm_stock_item s
        ON s.item_id = d.item_id
    WHERE d.plan_id = @plan_id
),
MasterItems AS
(
    SELECT
        s.item_code,
        MIN(s.item_id) AS master_item_id
    FROM tbm_stock_item s
    INNER JOIN RelevantItemCodes r
        ON r.item_code = s.item_code
    GROUP BY
        s.item_code
),
AllCodes AS
(
    SELECT DISTINCT
        m.master_item_id AS item_id,
        LTRIM(RTRIM(s.barcode)) AS barcode
    FROM tbm_stock_item s
    INNER JOIN MasterItems m
        ON m.item_code = s.item_code
    WHERE
        s.barcode IS NOT NULL
        AND LTRIM(RTRIM(s.barcode)) <> ''
    UNION
    SELECT
        m.master_item_id AS item_id,
        LTRIM(RTRIM(m.item_code)) AS barcode
    FROM MasterItems m
    WHERE
        m.item_code IS NOT NULL
        AND LTRIM(RTRIM(m.item_code)) <> ''
)
SELECT
    item_id,
    barcode
FROM AllCodes
ORDER BY
    item_id,
    barcode;
";
        List<BarcodeDto> result =
            new List<BarcodeDto>();
        using (SqlCommand command =
            new SqlCommand(sql, connection))
        {
            command.CommandTimeout =
                CommandTimeoutSeconds;
            command.Parameters.Add(
                "@plan_id",
                SqlDbType.Int
            ).Value = planId;
            using (SqlDataReader reader =
                command.ExecuteReader())
            {
                while (reader.Read())
                {
                    result.Add(
                        new BarcodeDto
                        {
                            item_id =
                                GetInt32(
                                    reader,
                                    "item_id"
                                ),
                            barcode =
                                GetString(
                                    reader,
                                    "barcode"
                                )
                        }
                    );
                }
            }
        }
        return result;
    }
    // =====================================================
    // Locations
    // =====================================================
    private List<LocationDto> GetLocations(
        SqlConnection connection,
        int planId
    )
    {
        /*
         * Resolve Location ตามลำดับความแม่นยำ:
         * 1) location_name ตรงแบบ exact
         * 2) location_code ตรงแบบ exact
         * 3) normalized location_name
         * 4) normalized location_code
         *
         * หาก priority ที่ดีที่สุดพบมากกว่า 1 location_id
         * จะไม่เลือก TOP (1) แบบสุ่ม แต่คืน Error ว่า Location กำกวม
         */
        const string sql = @"
;WITH LocationValues AS
(
    SELECT DISTINCT
        LTRIM(RTRIM(before_location)) AS location_value
    FROM dbo.tbt_plan_details
    WHERE plan_id = @plan_id
      AND before_location IS NOT NULL
      AND LTRIM(RTRIM(before_location)) <> ''

    UNION

    SELECT DISTINCT
        LTRIM(RTRIM(new_location)) AS location_value
    FROM dbo.tbt_plan_details
    WHERE plan_id = @plan_id
      AND new_location IS NOT NULL
      AND LTRIM(RTRIM(new_location)) <> ''
)
SELECT
    @plan_id AS plan_id,
    CASE WHEN matched.candidate_count = 1
         THEN matched.location_id
         ELSE NULL
    END AS location_id,
    c.location_value AS requested_location_value,
    CASE WHEN matched.candidate_count = 1
         THEN matched.location_code
         ELSE NULL
    END AS location_code,
    CASE WHEN matched.candidate_count = 1
         THEN ISNULL(
                  NULLIF(LTRIM(RTRIM(matched.location_name)), ''),
                  matched.location_code
              )
         ELSE NULL
    END AS location_name,
    ISNULL(matched.candidate_count, 0) AS candidate_count
FROM LocationValues c
OUTER APPLY
(
    SELECT TOP (1)
        ranked.match_priority
    FROM
    (
        SELECT
            x.location_id,
            CASE
                WHEN UPPER(LTRIM(RTRIM(ISNULL(x.location_name, '')))) =
                     UPPER(LTRIM(RTRIM(ISNULL(c.location_value, ''))))
                    THEN 1
                WHEN UPPER(LTRIM(RTRIM(ISNULL(x.location_code, '')))) =
                     UPPER(LTRIM(RTRIM(ISNULL(c.location_value, ''))))
                    THEN 2
                WHEN UPPER(REPLACE(REPLACE(REPLACE(
                         LTRIM(RTRIM(ISNULL(x.location_name, ''))),
                         '.', ''), '-', ''), ' ', '')) =
                     UPPER(REPLACE(REPLACE(REPLACE(
                         LTRIM(RTRIM(ISNULL(c.location_value, ''))),
                         '.', ''), '-', ''), ' ', ''))
                    THEN 3
                WHEN UPPER(REPLACE(REPLACE(REPLACE(
                         LTRIM(RTRIM(ISNULL(x.location_code, ''))),
                         '.', ''), '-', ''), ' ', '')) =
                     UPPER(REPLACE(REPLACE(REPLACE(
                         LTRIM(RTRIM(ISNULL(c.location_value, ''))),
                         '.', ''), '-', ''), ' ', ''))
                    THEN 4
                ELSE 99
            END AS match_priority
        FROM dbo.tbm_locations x
        WHERE ISNULL(x.is_active, 0) = 1
    ) ranked
    WHERE ranked.match_priority < 99
    ORDER BY ranked.match_priority
) best
OUTER APPLY
(
    SELECT
        COUNT(*) AS candidate_count,
        MIN(x.location_id) AS location_id,
        MIN(x.location_code) AS location_code,
        MIN(x.location_name) AS location_name
    FROM dbo.tbm_locations x
    WHERE ISNULL(x.is_active, 0) = 1
      AND
      CASE
          WHEN UPPER(LTRIM(RTRIM(ISNULL(x.location_name, '')))) =
               UPPER(LTRIM(RTRIM(ISNULL(c.location_value, ''))))
              THEN 1
          WHEN UPPER(LTRIM(RTRIM(ISNULL(x.location_code, '')))) =
               UPPER(LTRIM(RTRIM(ISNULL(c.location_value, ''))))
              THEN 2
          WHEN UPPER(REPLACE(REPLACE(REPLACE(
                   LTRIM(RTRIM(ISNULL(x.location_name, ''))),
                   '.', ''), '-', ''), ' ', '')) =
               UPPER(REPLACE(REPLACE(REPLACE(
                   LTRIM(RTRIM(ISNULL(c.location_value, ''))),
                   '.', ''), '-', ''), ' ', ''))
              THEN 3
          WHEN UPPER(REPLACE(REPLACE(REPLACE(
                   LTRIM(RTRIM(ISNULL(x.location_code, ''))),
                   '.', ''), '-', ''), ' ', '')) =
               UPPER(REPLACE(REPLACE(REPLACE(
                   LTRIM(RTRIM(ISNULL(c.location_value, ''))),
                   '.', ''), '-', ''), ' ', ''))
              THEN 4
          ELSE 99
      END = best.match_priority
) matched
ORDER BY c.location_value;
";

        List<LocationDto> result =
            new List<LocationDto>();

        List<string> missingValues =
            new List<string>();

        List<string> ambiguousValues =
            new List<string>();

        HashSet<int> addedLocationIds =
            new HashSet<int>();

        using (SqlCommand command =
            new SqlCommand(sql, connection))
        {
            command.CommandTimeout =
                CommandTimeoutSeconds;

            command.Parameters.Add(
                "@plan_id",
                SqlDbType.Int
            ).Value = planId;

            using (SqlDataReader reader =
                command.ExecuteReader())
            {
                while (reader.Read())
                {
                    int locationId =
                        GetInt32(
                            reader,
                            "location_id"
                        );

                    int candidateCount =
                        GetInt32(
                            reader,
                            "candidate_count"
                        );

                    string requestedValue =
                        GetString(
                            reader,
                            "requested_location_value"
                        );

                    if (candidateCount > 1)
                    {
                        ambiguousValues.Add(
                            requestedValue
                        );
                        continue;
                    }

                    if (locationId <= 0)
                    {
                        missingValues.Add(
                            requestedValue
                        );
                        continue;
                    }

                    // Plan อาจมีทั้งรูปแบบมีจุดและไม่มีจุด
                    // ซึ่ง resolve ไป location_id เดียวกัน ห้ามส่งซ้ำ
                    if (!addedLocationIds.Add(locationId))
                    {
                        continue;
                    }

                    result.Add(
                        new LocationDto
                        {
                            plan_id =
                                GetInt32(
                                    reader,
                                    "plan_id"
                                ),
                            location_id =
                                locationId,
                            location_code =
                                GetString(
                                    reader,
                                    "location_code"
                                ),
                            location_name =
                                GetString(
                                    reader,
                                    "location_name"
                                )
                        }
                    );
                }
            }
        }

        if (ambiguousValues.Count > 0)
        {
            throw new ApplicationException(
                "พบ Location ใน Plan ที่จับคู่ได้มากกว่า 1 รายการ: " +
                String.Join(", ", ambiguousValues.ToArray())
            );
        }

        if (missingValues.Count > 0)
        {
            throw new ApplicationException(
                "พบ Location ใน Plan ที่ไม่มีอยู่หรือไม่ได้ Active " +
                "ใน dbo.tbm_locations: " +
                String.Join(", ", missingValues.ToArray())
            );
        }

        return result;
    }
    // =====================================================
    // Plan Details
    // =====================================================
    private List<PlanDetailDto> GetPlanDetails(
        SqlConnection connection,
        int planId,
        Dictionary<int, int> itemMap
    )
    {
        const string sql = @"
SELECT
    d.plan_detail_id,
    d.plan_id,
    d.item_id,
    s.item_code,
    CASE WHEN matched.candidate_count = 1
         THEN matched.location_id
         ELSE NULL
    END AS location_id,
    ISNULL(matched.candidate_count, 0) AS candidate_count,
    req.requested_location,
    d.new_zone,
    d.before_zone,
    d.new_location,
    d.before_location,
    d.qty,
    d.qty_on_hand,
    d.qty_audit,
    d.check_date,
    d.checker,
    d.auditor,
    d.status_id,
    d.remark,
    d.barcode,
    d.udf1,
    d.udf2,
    d.udf3,
    d.audit_count,
    ISNULL(d.audit_count, 0) + 1 AS audit_round,
    d.create_date,
    d.create_by,
    d.update_date,
    d.update_by,
    d.is_confirm,
    d.is_change_location,
    d.is_check
FROM dbo.tbt_plan_details d
INNER JOIN dbo.tbm_stock_item s
    ON s.item_id = d.item_id
CROSS APPLY
(
    SELECT LTRIM(RTRIM(
        COALESCE(
            NULLIF(d.new_location, ''),
            d.before_location
        )
    )) AS requested_location
) req
OUTER APPLY
(
    SELECT TOP (1)
        ranked.match_priority
    FROM
    (
        SELECT
            x.location_id,
            CASE
                WHEN UPPER(LTRIM(RTRIM(ISNULL(x.location_name, '')))) =
                     UPPER(ISNULL(req.requested_location, ''))
                    THEN 1
                WHEN UPPER(LTRIM(RTRIM(ISNULL(x.location_code, '')))) =
                     UPPER(ISNULL(req.requested_location, ''))
                    THEN 2
                WHEN UPPER(REPLACE(REPLACE(REPLACE(
                         LTRIM(RTRIM(ISNULL(x.location_name, ''))),
                         '.', ''), '-', ''), ' ', '')) =
                     UPPER(REPLACE(REPLACE(REPLACE(
                         ISNULL(req.requested_location, ''),
                         '.', ''), '-', ''), ' ', ''))
                    THEN 3
                WHEN UPPER(REPLACE(REPLACE(REPLACE(
                         LTRIM(RTRIM(ISNULL(x.location_code, ''))),
                         '.', ''), '-', ''), ' ', '')) =
                     UPPER(REPLACE(REPLACE(REPLACE(
                         ISNULL(req.requested_location, ''),
                         '.', ''), '-', ''), ' ', ''))
                    THEN 4
                ELSE 99
            END AS match_priority
        FROM dbo.tbm_locations x
        WHERE ISNULL(x.is_active, 0) = 1
    ) ranked
    WHERE ranked.match_priority < 99
    ORDER BY ranked.match_priority
) best
OUTER APPLY
(
    SELECT
        COUNT(*) AS candidate_count,
        MIN(x.location_id) AS location_id
    FROM dbo.tbm_locations x
    WHERE ISNULL(x.is_active, 0) = 1
      AND
      CASE
          WHEN UPPER(LTRIM(RTRIM(ISNULL(x.location_name, '')))) =
               UPPER(ISNULL(req.requested_location, ''))
              THEN 1
          WHEN UPPER(LTRIM(RTRIM(ISNULL(x.location_code, '')))) =
               UPPER(ISNULL(req.requested_location, ''))
              THEN 2
          WHEN UPPER(REPLACE(REPLACE(REPLACE(
                   LTRIM(RTRIM(ISNULL(x.location_name, ''))),
                   '.', ''), '-', ''), ' ', '')) =
               UPPER(REPLACE(REPLACE(REPLACE(
                   ISNULL(req.requested_location, ''),
                   '.', ''), '-', ''), ' ', ''))
              THEN 3
          WHEN UPPER(REPLACE(REPLACE(REPLACE(
                   LTRIM(RTRIM(ISNULL(x.location_code, ''))),
                   '.', ''), '-', ''), ' ', '')) =
               UPPER(REPLACE(REPLACE(REPLACE(
                   ISNULL(req.requested_location, ''),
                   '.', ''), '-', ''), ' ', ''))
              THEN 4
          ELSE 99
      END = best.match_priority
) matched
WHERE d.plan_id = @plan_id
ORDER BY d.plan_detail_id;
";
        List<PlanDetailDto> result =
            new List<PlanDetailDto>();

        List<string> missingDetails =
            new List<string>();

        List<string> ambiguousDetails =
            new List<string>();

        using (SqlCommand command =
            new SqlCommand(sql, connection))
        {
            command.CommandTimeout =
                CommandTimeoutSeconds;
            command.Parameters.Add(
                "@plan_id",
                SqlDbType.Int
            ).Value = planId;
            using (SqlDataReader reader =
                command.ExecuteReader())
            {
                while (reader.Read())
                {
                    int sourceItemId =
                        GetInt32(
                            reader,
                            "item_id"
                        );
                    int masterItemId =
                        sourceItemId;
                    if (itemMap.ContainsKey(sourceItemId))
                    {
                        masterItemId =
                            itemMap[sourceItemId];
                    }

                    int planDetailId =
                        GetInt32(
                            reader,
                            "plan_detail_id"
                        );

                    int locationId =
                        GetInt32(
                            reader,
                            "location_id"
                        );

                    int candidateCount =
                        GetInt32(
                            reader,
                            "candidate_count"
                        );

                    string requestedLocation =
                        GetString(
                            reader,
                            "requested_location"
                        );

                    if (candidateCount > 1)
                    {
                        ambiguousDetails.Add(
                            planDetailId + ":" + requestedLocation
                        );
                        continue;
                    }

                    if (locationId <= 0)
                    {
                        missingDetails.Add(
                            planDetailId + ":" + requestedLocation
                        );
                        continue;
                    }

                    result.Add(
                        new PlanDetailDto
                        {
                            plan_detail_id =
                                planDetailId,
                            plan_id =
                                GetInt32(
                                    reader,
                                    "plan_id"
                                ),
                            item_id =
                                masterItemId,
                            source_item_id =
                                sourceItemId,
                            item_code =
                                GetString(
                                    reader,
                                    "item_code"
                                ),
                            location_id =
                                locationId,
                            new_zone =
                                GetString(
                                    reader,
                                    "new_zone"
                                ),
                            before_zone =
                                GetString(
                                    reader,
                                    "before_zone"
                                ),
                            new_location =
                                GetString(
                                    reader,
                                    "new_location"
                                ),
                            before_location =
                                GetString(
                                    reader,
                                    "before_location"
                                ),
                            qty =
                                GetDecimal(
                                    reader,
                                    "qty"
                                ),
                            qty_on_hand =
                                GetDecimal(
                                    reader,
                                    "qty_on_hand"
                                ),
                            qty_audit =
                                GetDecimal(
                                    reader,
                                    "qty_audit"
                                ),
                            check_date =
                                GetNullableDateTime(
                                    reader,
                                    "check_date"
                                ),
                            checker =
                                GetString(
                                    reader,
                                    "checker"
                                ),
                            auditor =
                                GetString(
                                    reader,
                                    "auditor"
                                ),
                            status_id =
                                GetNullableInt32(
                                    reader,
                                    "status_id"
                                ),
                            remark =
                                GetString(
                                    reader,
                                    "remark"
                                ),
                            barcode =
                                GetString(
                                    reader,
                                    "barcode"
                                ),
                            udf1 =
                                GetString(
                                    reader,
                                    "udf1"
                                ),
                            udf2 =
                                GetString(
                                    reader,
                                    "udf2"
                                ),
                            udf3 =
                                GetString(
                                    reader,
                                    "udf3"
                                ),
                            audit_count =
                                GetNullableInt32(
                                    reader,
                                    "audit_count"
                                ) ?? 0,
                            audit_round =
                                GetInt32(
                                    reader,
                                    "audit_round"
                                ),
                            create_date =
                                GetNullableDateTime(
                                    reader,
                                    "create_date"
                                ),
                            create_by =
                                GetNullableInt32(
                                    reader,
                                    "create_by"
                                ),
                            update_date =
                                GetNullableDateTime(
                                    reader,
                                    "update_date"
                                ),
                            update_by =
                                GetNullableInt32(
                                    reader,
                                    "update_by"
                                ),
                            is_confirm =
                                GetNullableInt32(
                                    reader,
                                    "is_confirm"
                                ) ?? 0,
                            is_change_location =
                                GetNullableInt32(
                                    reader,
                                    "is_change_location"
                                ) ?? 0,
                            is_check =
                                GetNullableInt32(
                                    reader,
                                    "is_check"
                                ) ?? 0
                        }
                    );
                }
            }
        }

        if (ambiguousDetails.Count > 0)
        {
            throw new ApplicationException(
                "พบ Plan Detail ที่ Location จับคู่ได้มากกว่า 1 รายการ " +
                "(plan_detail_id:location): " +
                String.Join(", ", ambiguousDetails.ToArray())
            );
        }

        if (missingDetails.Count > 0)
        {
            throw new ApplicationException(
                "พบ Plan Detail ที่ไม่สามารถหา location_id ได้ " +
                "(plan_detail_id:location): " +
                String.Join(", ", missingDetails.ToArray())
            );
        }

        return result;
    }
    // =====================================================
    // Reader Helpers
    // =====================================================
    private int GetInt32(
        SqlDataReader reader,
        string columnName
    )
    {
        object value = reader[columnName];
        if (
            value == null ||
            value == DBNull.Value
        )
        {
            return 0;
        }
        return Convert.ToInt32(value);
    }
    private int? GetNullableInt32(
        SqlDataReader reader,
        string columnName
    )
    {
        object value = reader[columnName];
        if (
            value == null ||
            value == DBNull.Value
        )
        {
            return null;
        }
        return Convert.ToInt32(value);
    }
    private decimal GetDecimal(
        SqlDataReader reader,
        string columnName
    )
    {
        object value = reader[columnName];
        if (
            value == null ||
            value == DBNull.Value
        )
        {
            return 0M;
        }
        return Convert.ToDecimal(value);
    }
    private string GetString(
        SqlDataReader reader,
        string columnName
    )
    {
        object value = reader[columnName];
        if (
            value == null ||
            value == DBNull.Value
        )
        {
            return String.Empty;
        }
        return Convert.ToString(value).Trim();
    }
    private DateTime? GetNullableDateTime(
        SqlDataReader reader,
        string columnName
    )
    {
        object value = reader[columnName];
        if (
            value == null ||
            value == DBNull.Value
        )
        {
            return null;
        }
        return Convert.ToDateTime(value);
    }
    // =====================================================
    // JSON
    // =====================================================
    private JavaScriptSerializer CreateSerializer()
    {
        JavaScriptSerializer serializer =
            new JavaScriptSerializer();
        serializer.MaxJsonLength =
            Int32.MaxValue;
        serializer.RecursionLimit =
            100;
        return serializer;
    }
    private void WriteJson(
        HttpContext context,
        JavaScriptSerializer serializer,
        object data,
        int statusCode
    )
    {
        JsonResponseHelper.Write(context, serializer, data, statusCode);
    }

    public bool IsReusable
    {
        get
        {
            return false;
        }
    }
}
// =========================================================
// Request Model
// =========================================================
public class DownloadRequest
{
    public int plan_id
    {
        get;
        set;
    }
}
// =========================================================
// Response Models
// =========================================================
public class DownloadResponse
{
    public bool success
    {
        get;
        set;
    }
    public string message
    {
        get;
        set;
    }
    public PlanDto plan
    {
        get;
        set;
    }
    public List<ItemDto> items
    {
        get;
        set;
    }
    public List<BarcodeDto> barcodes
    {
        get;
        set;
    }
    public List<LocationDto> locations
    {
        get;
        set;
    }
    public List<PlanDetailDto> details
    {
        get;
        set;
    }
    public DownloadSummaryDto summary
    {
        get;
        set;
    }
}
public class ErrorResponse
{
    public bool success
    {
        get;
        set;
    }
    public string message
    {
        get;
        set;
    }
    public string error
    {
        get;
        set;
    }
}
public class DownloadSummaryDto
{
    public int item_count
    {
        get;
        set;
    }
    public int barcode_count
    {
        get;
        set;
    }
    public int location_count
    {
        get;
        set;
    }
    public int detail_count
    {
        get;
        set;
    }
}
public class PlanDto
{
    public int plan_id
    {
        get;
        set;
    }
    public string plan_code
    {
        get;
        set;
    }
    public string plan_details
    {
        get;
        set;
    }
    public DateTime? plan_check_date
    {
        get;
        set;
    }
    public string plan_status
    {
        get;
        set;
    }
    public string udf1
    {
        get;
        set;
    }
    public string udf2
    {
        get;
        set;
    }
    public string udf3
    {
        get;
        set;
    }
    public DateTime? create_date
    {
        get;
        set;
    }
    public int? create_by
    {
        get;
        set;
    }
    public DateTime? update_date
    {
        get;
        set;
    }
    public int? update_by
    {
        get;
        set;
    }
    public int is_export
    {
        get;
        set;
    }
}
public class ItemDto
{
    public int item_id
    {
        get;
        set;
    }
    public string item_code
    {
        get;
        set;
    }
    public string item_name
    {
        get;
        set;
    }
    public string category
    {
        get;
        set;
    }
    public decimal unit_rate
    {
        get;
        set;
    }
    public decimal qty
    {
        get;
        set;
    }
    public string uom
    {
        get;
        set;
    }
    public decimal unit_cost
    {
        get;
        set;
    }
    public string batching_unit
    {
        get;
        set;
    }
    public decimal batching_factor
    {
        get;
        set;
    }
    public int is_active
    {
        get;
        set;
    }
}
public class BarcodeDto
{
    public int item_id
    {
        get;
        set;
    }
    public string barcode
    {
        get;
        set;
    }
}
public class LocationDto
{
    public int plan_id
    {
        get;
        set;
    }
    public int location_id
    {
        get;
        set;
    }
    public string location_code
    {
        get;
        set;
    }
    public string location_name
    {
        get;
        set;
    }
}
public class PlanDetailDto
{
    public int plan_detail_id
    {
        get;
        set;
    }
    public int plan_id
    {
        get;
        set;
    }
    /*
     * Master Item ID ที่ Android ใช้
     */
    public int item_id
    {
        get;
        set;
    }
    /*
     * Item ID เดิมจาก SQL Server
     * เก็บไว้ใช้ตรวจสอบและ Sync ในอนาคต
     */
    public int source_item_id
    {
        get;
        set;
    }
    public string item_code
    {
        get;
        set;
    }
    public int location_id
    {
        get;
        set;
    }
    public string new_zone
    {
        get;
        set;
    }
    public string before_zone
    {
        get;
        set;
    }
    public string new_location
    {
        get;
        set;
    }
    public string before_location
    {
        get;
        set;
    }
    public decimal qty
    {
        get;
        set;
    }
    public decimal qty_on_hand
    {
        get;
        set;
    }
    public decimal qty_audit
    {
        get;
        set;
    }
    public DateTime? check_date
    {
        get;
        set;
    }
    public string checker
    {
        get;
        set;
    }
    public string auditor
    {
        get;
        set;
    }
    public int? status_id
    {
        get;
        set;
    }
    public string remark
    {
        get;
        set;
    }
    public string barcode
    {
        get;
        set;
    }
    public string udf1
    {
        get;
        set;
    }
    public string udf2
    {
        get;
        set;
    }
    public string udf3
    {
        get;
        set;
    }
    public int audit_count
    {
        get;
        set;
    }
    public int audit_round
    {
        get;
        set;
    }
    public DateTime? create_date
    {
        get;
        set;
    }
    public int? create_by
    {
        get;
        set;
    }
    public DateTime? update_date
    {
        get;
        set;
    }
    public int? update_by
    {
        get;
        set;
    }
    public int is_confirm
    {
        get;
        set;
    }
    public int is_change_location
    {
        get;
        set;
    }
    public int is_check
    {
        get;
        set;
    }
}