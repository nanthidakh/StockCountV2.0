<%@ WebHandler Language="C#" Class="get_config" %>
using System;
using System.Web;
using System.Web.Script.Serialization;
using System.Collections.Generic;
using System.Text;

public class get_config : IHttpHandler
{
    public void ProcessRequest(HttpContext context)
    {
        context.Response.Clear();
        context.Response.ContentType = "application/json";
        context.Response.ContentEncoding = Encoding.UTF8;
        context.Response.Charset = "utf-8";
        context.Response.TrySkipIisCustomErrors = true;

        try
        {
            // Staff list กลาง ใช้ร่วมกันทุกสาขา แก้ที่จุดนี้เพียงครั้งเดียว
            var staffList = new List<string>
            {
                "CT",
                "EE",
                "HT",
                "HW",
                "MI",
                "PA",
                "PB",
                "PT",
                "SF"
            };

            var branches = new List<object>
            {
                new
                {
                    branch_name = "Bowin",
                    db_server_ip = "10.1.1.3",
                    db_name = "HWKING_BW",
                    db_user = "sa",
                    db_password = "Hwkingp@ss",
                    count_month = "08/2026",
                    iis_server_ip = context.Request.Url.Host
                },
                new
                {
                    branch_name = "Maptapud",
                    db_server_ip = "10.1.1.3",
                    db_name = "HWKING_MP",
                    db_user = "sa",
                    db_password = "Hwkingp@ss",
                    count_month = "08/2026",
                    iis_server_ip = context.Request.Url.Host
                }
            };

            var response = new
            {
                success = true,
                staff_list = staffList,
                branches = branches
            };

            JavaScriptSerializer js = new JavaScriptSerializer();
            context.Response.Write(js.Serialize(response));
        }
        catch (Exception ex)
        {
            JavaScriptSerializer js = new JavaScriptSerializer();
            context.Response.StatusCode = 500;
            context.Response.Write(js.Serialize(new
            {
                success = false,
                error = ex.Message
            }));
        }
    }

    public bool IsReusable
    {
        get { return false; }
    }
}
