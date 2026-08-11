<%@ WebHandler Language="C#" Class="GetSyncStatusHandler" %>

using System;
using System.Configuration;
using System.Data;
using System.Data.SqlClient;
using System.IO;
using System.Web;
using System.Web.Script.Serialization;

public class GetSyncStatusHandler : IHttpHandler
{
    private sealed class RequestData
    {
        public string device_id { get; set; }
        public int plan_id { get; set; }
        public string sync_batch_guid { get; set; }
    }

    public void ProcessRequest(HttpContext context)
    {
        JsonResponseHelper.Prepare(context);
        var json = new JavaScriptSerializer();

        try
        {
            string body;
            using (var reader = new StreamReader(context.Request.InputStream))
                body = reader.ReadToEnd();

            RequestData request = json.Deserialize<RequestData>(body);
            if (request == null)
                throw new ApplicationException("Invalid JSON request.");

            Guid deviceId;
            if (!Guid.TryParse(request.device_id, out deviceId))
                throw new ApplicationException("Invalid device_id.");

            if (request.plan_id <= 0)
                throw new ApplicationException("Invalid plan_id.");

            Guid syncBatchGuid;
            if (!Guid.TryParse(request.sync_batch_guid, out syncBatchGuid))
                throw new ApplicationException("Invalid sync_batch_guid.");

            int waiting = 0;
            int processing = 0;
            int successCount = 0;
            int errorCount = 0;
            int totalCount = 0;
            DateTime? lastReceived = null;
            DateTime? lastProcessed = null;

            using (var connection = new SqlConnection(GetConnectionString()))
            using (var command = new SqlCommand(@"
SELECT
    COUNT(*) AS total_count,
    SUM(CASE WHEN process_status = 'WAITING' THEN 1 ELSE 0 END) AS waiting_count,
    SUM(CASE WHEN process_status = 'PROCESSING' THEN 1 ELSE 0 END) AS processing_count,
    SUM(CASE WHEN process_status = 'SUCCESS' THEN 1 ELSE 0 END) AS success_count,
    SUM(CASE WHEN process_status = 'ERROR' THEN 1 ELSE 0 END) AS error_count,
    MAX(received_at) AS last_received,
    MAX(processed_at) AS last_processed
FROM dbo.tbt_sync_count_staging
WHERE device_id = @device_id
  AND plan_id = @plan_id
  AND sync_batch_guid = @sync_batch_guid;", connection))
            {
                command.CommandTimeout = 30;
                command.Parameters.Add("@device_id", SqlDbType.UniqueIdentifier).Value = deviceId;
                command.Parameters.Add("@plan_id", SqlDbType.Int).Value = request.plan_id;
                command.Parameters.Add("@sync_batch_guid", SqlDbType.UniqueIdentifier).Value = syncBatchGuid;

                connection.Open();
                using (var reader = command.ExecuteReader())
                {
                    if (reader.Read())
                    {
                        totalCount = reader.IsDBNull(0) ? 0 : Convert.ToInt32(reader[0]);
                        waiting = reader.IsDBNull(1) ? 0 : Convert.ToInt32(reader[1]);
                        processing = reader.IsDBNull(2) ? 0 : Convert.ToInt32(reader[2]);
                        successCount = reader.IsDBNull(3) ? 0 : Convert.ToInt32(reader[3]);
                        errorCount = reader.IsDBNull(4) ? 0 : Convert.ToInt32(reader[4]);
                        lastReceived = reader.IsDBNull(5) ? (DateTime?)null : Convert.ToDateTime(reader[5]);
                        lastProcessed = reader.IsDBNull(6) ? (DateTime?)null : Convert.ToDateTime(reader[6]);
                    }
                }
            }

            string statusMessage;
            if (errorCount > 0)
                statusMessage = "Process มีรายการผิดพลาด";
            else if (processing > 0)
                statusMessage = "กำลัง Process";
            else if (waiting > 0)
                statusMessage = "ส่งแล้ว รอ Process";
            else if (successCount > 0)
                statusMessage = "Process สำเร็จ";
            else
                statusMessage = "ยังไม่มีข้อมูลใน Batch";
            JsonResponseHelper.Write(context, json, new
            {
                success = true,
                has_batch = totalCount > 0,
                waiting_count = waiting,
                processing_count = processing,
                success_count = successCount,
                error_count = errorCount,
                last_received = lastReceived,
                last_processed = lastProcessed,
                status_message = statusMessage
            }, 200);
        }
        catch (Exception ex)
        {
            JsonResponseHelper.Write(context, json, new
            {
                success = false,
                error_type = ex.GetType().Name,
                message = ex.Message
            }, 200);
        }
    }

    private static string GetConnectionString()
    {
        string value = ConfigurationManager.AppSettings["strConn"];
        if (String.IsNullOrWhiteSpace(value))
            throw new ConfigurationErrorsException("Missing appSettings key: strConn in Web.config.");
        return value.Trim();
    }

    public bool IsReusable { get { return false; } }
}
