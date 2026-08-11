<%@ WebHandler Language="C#" Class="GetProductsHandler" %>
using System;
using System.Web;
using System.Data.SqlClient;
using System.Web.Script.Serialization;

public class GetProductsHandler : IHttpHandler {
    public void ProcessRequest(HttpContext context) {
        // เพิ่มเวลา Timeout ให้ Server ทำงานได้นานขึ้น
        context.Server.ScriptTimeout = 600; 
        
        string jsonString = new System.IO.StreamReader(context.Request.InputStream).ReadToEnd();
        var serializer = new JavaScriptSerializer();
        var data = serializer.Deserialize<System.Collections.Generic.Dictionary<string, string>>(jsonString);

        if (data == null || !data.ContainsKey("db_server_ip") || !data.ContainsKey("db_name")) {
            context.Response.StatusCode = 400;
            context.Response.Write("Error: Missing database config parameters.");
            return;
        }

        string connString = string.Format("Server={0};Database={1};User Id=sa;Password=Hwkingp@ss;", 
                            data["db_server_ip"], data["db_name"]);
        string month = data.ContainsKey("month") ? data["month"] : "08/2026";
        
        // Query ปกติโดยไม่มี top 5000 (ดึงทั้งหมด)
        string query = @"SELECT ISNULL(b.BARCODE, ''), ISNULL(a.code, ''), ISNULL(a.NAME, ''), 
                                ISNULL(f.SNAME, ''), ISNULL(c.LNAME, '') 
                         FROM CSPRODUCT a 
                         LEFT JOIN csbarcode b ON a.code = b.PRODUCTCODE
                         LEFT JOIN CSUNIT c ON a.STOCKUNIT = c.ID
                         LEFT JOIN CSDIM5 f ON a.DIM5 = f.ID
                         WHERE a.SYSDOCFLAG = 0 AND b.BARCODE IS NOT NULL";

        context.Response.ContentType = "application/json";
        context.Response.Write("["); // เริ่มต้น JSON Array
        bool first = true;

        try {
            using (SqlConnection conn = new SqlConnection(connString)) {
                SqlCommand cmd = new SqlCommand(query, conn);
                conn.Open();
                using (SqlDataReader rdr = cmd.ExecuteReader()) {
                    while (rdr.Read()) {
                        if (!first) context.Response.Write(",");
                        
                        var item = new object[] { 
                            rdr.IsDBNull(0) ? "" : rdr[0].ToString(),
                            rdr.IsDBNull(1) ? "" : rdr[1].ToString(),
                            rdr.IsDBNull(2) ? "" : rdr[2].ToString(),
                            rdr.IsDBNull(3) ? "" : rdr[3].ToString(),
                            month,
                            rdr.IsDBNull(4) ? "" : rdr[4].ToString()
                        };
                        context.Response.Write(serializer.Serialize(item));
                        first = false;
                    }
                }
            }
        } catch (Exception ex) {
            context.Response.Write("{\"error\": \"" + ex.Message + "\"}");
        }
        
        context.Response.Write("]"); // จบ JSON Array
        context.Response.Flush();
        context.Response.End();
    }
    public bool IsReusable { get { return false; } }
}