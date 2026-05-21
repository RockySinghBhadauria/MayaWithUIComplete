# Maya Stored Procedure Definitions

Dumped via `sp_helptext` from production SQL Server. Used to audit insert/update behavior before wiring UI parsers to call these SPs.

**Database:** see `.env` (DB_NAME)

---

## `sp_Company_Finaicials_FiscalYear_End_IU_MAYA`

```sql
      
-- =============================================        
-- Author: Abhijit Deshmukh        
-- Create date: 26/07/2019       
-- Description: Insert into Finaicials FiscalYear & FiscalYearEnd.        
        
/*        
Change log         
--------------------------------------------------------------------        
 Abhijit Deshmukh -  Updated the SPROC to insert row in Tracking_Data_Entry table as well.        
 Abhijit Deshmukh - Update SPROC to keep track of CreatedBy column      
      
 Abhijit Deshmukh - Add,Update, Created By in financial table      
        
*/        
        
-- =============================================

        
CREATE PROCEDURE [dbo].[sp_Company_Finaicials_FiscalYear_End_IU_MAYA]        
  (        
   @Company_ID INT,        
   @FiscalYearEnd DateTime,        
   @FiscalYear INT,      
   @UpdatedBy varchar(100)=''      
  )        
AS        
    
BEGIN       
     
 IF(NOT EXISTS(SELECT * FROM Financials WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear))        
 BEGIN        
    INSERT INTO Financials(Company_ID,FiscalYear,FiscalYearEnd, CreatedBy,UpdatedBy,UpdatedDate,SprocName)        
    VALUES(@Company_ID,@FiscalYear,@FiscalYearEnd, 'MAYA',@UpdatedBy,GETDATE(),'Insert_sp_Company_Finaicials_FiscalYear_End_IU')        
 END 
 
 IF(EXISTS(SELECT * FROM Financials WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear))        
 BEGIN        
         UPDATE Financials       
	SET      
		FiscalYear= @FiscalYear,
		FiscalYearEnd = @FiscalYearEnd, 
		UpdatedBy =  'MAYA',
		UpdatedDate =  GETDATE()
		where Company_ID =  @Company_ID and FiscalYear = @FiscalYear
 END     
        
 IF(NOT EXISTS(SELECT * FROM Company_FiscalYear WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear))        
 BEGIN        
    INSERT INTO Company_FiscalYear(Company_ID,FiscalYear,CreatedBy)        
    VALUES(@Company_ID,@FiscalYear,'MAYA')        
 END        
        
 IF(NOT EXISTS(SELECT * FROM Tracking_Data_Entry WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear))        
 BEGIN        
    INSERT INTO Tracking_Data_Entry(Company_ID,FiscalYear,Perquisites_entered_Name)        
    VALUES(@Company_ID,@FiscalYear,'MAYA')        
 END        
        
END 
```

**Behavior summary:** INSERT=True, UPDATE=True, IF-EXISTS branch=False

---

## `sp_wk_SummaryComp_IU_MAYA`

```sql
        
/*                  
 Author: Abhijit Deshmukh                 
 Created: 23/10/2019                 
 Description:                 
          Changelog                  
======================================    
- MAKE ENRTY FOR ALL OFFICERS IN OFFICER TABLE WITH LATEST FISCAL YEAR                 
- Abhijit Deshmukh - Added Update section to update the wk_SummaryComp table with new values(previously only insert section)  
- Abhijit Deshmukh - Update the Last_Officer_ID in wk_SummaryComp for automatic Create/Update Officers.


*/

                  
CREATE PROCEDURE [dbo].[sp_wk_SummaryComp_IU_MAYA]            
(    
		 @Officer_ID int = NULL ,             
		 @ParsedName nvarchar(200) = NULL,            
		 @OfficerName nvarchar(200) = NULL,             
		 @FiscalYear int = null,             
		 @Salary money = null,             
		 @Bonus money = null,             
		 @Stock_Award money = null,            
		 @Option_Awards money = null,            
		 @Non_Eq_Incentive_Plan_Comp money = null,            
		 @Chg_PensionValue_NQDC_Earnings money = null,            
		 @Chg_Retention_Plan_Value money = null,            
		 @All_Other money = null,            
		 @Total money = null,            
		 @TagName nvarchar(50)=NULL,            
		 @Company_ID int = null,            
		 @CreateDate datetime = null,            
		 @CreatedBy varchar(50) = NULL,        
		 @Role_ID1 int = NULL        
    )                  
AS                   
    BEGIN             
 IF(@Officer_ID IS NOT NULL)          
  BEGIN          
	   --SET @Role_ID1 = (select Role_ID1 from Officer where Company_ID =@Company_ID and FiscalYear=(@FiscalYear - 1) and  LTRIM(RTRIM(OfficerName)) like '%'+@ParsedName+'%');          
	   SET @Role_ID1 = (select Role_ID1 from Officer where Company_ID =@Company_ID AND FiscalYear=(@FiscalYear - 1) AND Officer_ID =@Officer_ID);         
  END                
    
IF NOT EXISTS(select 1 from wk_SummaryComp where OfficerName = @OfficerName and Company_ID = @Company_ID and FiscalYear = @FiscalYear)  
 BEGIN  
  INSERT INTO wk_SummaryComp            
    (            
		  Officer_ID,            
		  ParsedName,            
		  OfficerName,            
		  FiscalYear,            
		  Salary,            
		  Bonus,            
		  Stock_Award,            
		  Option_Awards,            
		  Non_Eq_Incentive_Plan_Comp,            
		  Chg_PensionValue_NQDC_Earnings,            
		  Chg_Retention_Plan_Value,            
		  All_Other,            
		  Total,            
		  TagName,            
		  Company_ID,            
		  CreateDate,            
		  CreatedBy,        
		  Role_ID1 ,  
		  LastUpdatedBy  
    
    )             
    values             
    (            
		  @Officer_ID,            
		  @ParsedName,            
		  @OfficerName,            
		  @FiscalYear,            
		  @Salary,            
		  @Bonus,            
		  @Stock_Award,            
		  @Option_Awards,            
		  @Non_Eq_Incentive_Plan_Comp,            
		  @Chg_PensionValue_NQDC_Earnings,            
		  @Chg_Retention_Plan_Value,            
		  @All_Other,            
		  @Total,            
		  @TagName,            
		  @Company_ID,            
		  @CreateDate,            
		  @CreatedBy,        
		  @Role_ID1,  
		  'MAYA'     
           
    )     
  
 END  
  
ELSE  
 BEGIN  
   Declare @Officer_ID_db int  = (select Officer_ID from wk_SummaryComp where OfficerName = @OfficerName and Company_ID = @Company_ID and FiscalYear = @FiscalYear)  
   UPDATE  dbo.wk_SummaryComp              
   SET           
		 ParsedName = @ParsedName,    
		 Salary = @Salary,  
		 Bonus  = @Bonus,  
		 Stock_Award = @Stock_Award,  
		 Option_Awards = @Option_Awards,  
		 Non_Eq_Incentive_Plan_Comp = @Non_Eq_Incentive_Plan_Comp,  
		 Chg_PensionValue_NQDC_Earnings = @Chg_PensionValue_NQDC_Earnings,  
		 Chg_Retention_Plan_Value = @Chg_Retention_Plan_Value,  
		 All_Other = @All_Other,  
		 Total = @Total,  
		 TagName = @TagName,   
		 CreateDate = @CreateDate,  
		 CreatedBy = @CreatedBy,  
		 Role_ID1 = @Role_ID1 ,  
		 LastUpdateDate = GETDATE(),  
		 LastUpdatedBy = 'MAYA'                                              
       
		 WHERE Officer_ID = @Officer_ID_db and Company_ID = @Company_ID and FiscalYear = @FiscalYear;    
  
 END  
  
  
  
-- Update the Last_Officer_ID in wk_SummaryComp for automatic Create/Update Officers    
    
Declare @lastFYA int = (SELECT YEAR(getdate())- 1)      
UPDATE      
		wk_SummaryComp      
	SET      
		wk_SummaryComp.Last_Officer_ID = Officer.Officer_ID      
	FROM      
		Officer       
		INNER JOIN wk_SummaryComp       
		ON Officer.OfficerName = wk_SummaryComp.OfficerName      
	    and wk_SummaryComp.Company_ID = @Company_ID and wk_SummaryComp.FiscalYear = @lastFYA       
		and Officer.Company_ID = @Company_ID and Officer.FiscalYear = @lastFYA -1       
        
  --END              
END 
```

**Behavior summary:** INSERT=True, UPDATE=True, IF-EXISTS branch=True

---

## `sp_wk_SummaryComp_U_MAYA`

```sql
  
/*          
 Author: Abhijit Deshmukh          
 Created: 26/07/2019          
 Description: This SPROC updates the wk_SummaryComp columns using the ID. Depending on the Officer_ID           
 parameters provided, will Update, Insert or Insert with Copy forward from Last FY.          
 For the web Data Entry app.          
         Changelog          
======================================          
01/14/2014  BT  New SPROC          
01/17/2014  BT  When we INSERT into Officer and return the new Officer_ID, we need to Update wk_SummaryComp          
    so subsequent execution of this sproc will Update the Officer row rather than insert a new one.          
01/18/2014  BT  Removed columns we don't need to update: Footnote, Scan_ID, ParsedName, Chg_Retention_Plan_Value.          
    Also defaulting Officer.Role_ID1 to 0 and added columns to copy forward from Last year Officer row.          
01/10/2015  BT  If the company is published, only update the tags... for backfilling tags in prior years.          
03/17/2015  BT  Added logic to set Scanlog status to Officer Matched when this runs.          
03/24/2015  BT  Add Sample Executive insert, set default Role_ID1 = 14 (unspecified)          
03/25/2015  BT  Add CreatedBy, LastUpdatedBy          
04/08/2015  BT  Add ISNULL check to setting Role_ID and PP_Role_ID values in copy forward.          
04/14/2015  BT  Changed 'Sample_Executive' to 'Sample Executive'          
05/29/2015  BT  Added logic to insert a new row in wk_SummaryComp.          
06/24/2015  BT  Fix handling of wk ID when checking Officer existence. Add IF branching to handle new wk row insert ID. Fix Scan_ID capture.          
07/14/2015  BT  Fix multiple rows retrieved from Scanlog. Had to filter out Cancelled filings.          
09/12/2016  AK  Fixed multiple rows retrieval for @Publish FROM Company_FiscalYear.       
4/12/2017   SC  Changes made to match office Name (REPLACE blank spaces and dash)    
1/13/2017 SC ADDED @Prev_Officer_ID O UPDATE ROLES WITH PREVIOUS OFFICER    
*/     
     
CREATE PROCEDURE [dbo].[sp_wk_SummaryComp_U_MAYA]          
    (          
      @ID INT,          
      @TagName NVARCHAR(50),          
      @Last_Officer_ID INT,          
      @Officer_ID INT,          
      @Company_ID INT,          
      @FiscalYear INT,          
      @OfficerName NVARCHAR(200),          
      @Salary MONEY = NULL,          
      @Bonus MONEY = NULL,          
      @Stock_Award MONEY = NULL,          
      @Option_Awards MONEY = NULL,          
      @Non_Eq_Incentive_Plan_Comp MONEY = NULL,          
      @Chg_PensionValue_NQDC_Earnings MONEY = NULL,          
      @All_Other MONEY = NULL,          
      @Total MONEY = NULL,          
      @UserID NVARCHAR(50) = NULL          
    )          
AS     
BEGIN      
 DECLARE @New_wk_ID INT, @New_Officer_ID INT, @Cur_Officer_ID INT, @Sample_Exec_ID INT, @Published INT, @Scan_ID INT,     
 @Prev_Officer_ID INT = CASE WHEN @Last_Officer_ID = 0 THEN @Officer_ID ELSE @Last_Officer_ID END;       
 SET @Published = (SELECT Publish FROM Company_FiscalYear WHERE Company_ID= @Company_ID AND FiscalYear = @FiscalYear and Publish is not null);      -- Check if this is a backfill situation    
 SET @Scan_ID = (SELECT Scan_ID FROM Scanlog WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear AND Scan_Status NOT IN ('Cancelled', 'Not a Proxy', 'Version Issue') AND Filing_Type LIKE 'DEF%');          
 UPDATE dbo.Scanlog          
 SET Scan_Status = 'Officer Matched',          
 MatchedDate = getdate(),          
 MatchedBy = @UserID          
 WHERE Scan_ID = @Scan_ID;          
 -- Create Sample Executive role if none exists for current year.          
 BEGIN          
  SET @Sample_Exec_ID = ISNULL((SELECT Officer_ID FROM Officer WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear AND Role_ID1=43),0)          
  IF @Sample_Exec_ID = 0        
  BEGIN      
   INSERT INTO Officer           
    (          
     Company_ID,          
     FiscalYear,          
     OfficerName,          
     Role_ID1,          
Company_Title,          
     PP_Role_ID1,          
     PP_Company_Title,          
     Age,          
     Salary,          
     Bonus,          
     Scan_ID,          
     CreatedBy,          
     LastUpdatedBy          
    )          
   SELECT @Company_ID,          
     @FiscalYear,          
     'Sample Executive',          
     43,          
     'Sample Executive',          
     43,          
     'Sample Executive',          
     Age,          
     Salary,          
     Bonus,       
     @Scan_ID,          
     ISNULL(@UserID,'CLIC'),          
     ISNULL(@UserID,'CLIC')          
   FROM Sample_Officer           
   WHERE FiscalYear = @FiscalYear          
   SET @Sample_Exec_ID = SCOPE_IDENTITY();        
  END      
 END;          
 --Update wk_SummaryComp with changes from Web form          
 BEGIN          
  IF ISNULL(@ID,0) <> 0       
  BEGIN       
   UPDATE  dbo.wk_SummaryComp          
   SET            
     TagName = @TagName,          
     Scan_ID = ISNULL(Scan_ID, @Scan_ID),          
     Last_Officer_ID = @Last_Officer_ID,          
     Officer_ID = @Officer_ID,          
     Company_ID = @Company_ID,          
     FiscalYear = @FiscalYear,          
     OfficerName = @OfficerName,          
     Salary = @Salary,          
     Bonus = @Bonus,          
     Stock_Award = @Stock_Award,          
     Option_Awards = @Option_Awards,          
     Non_Eq_Incentive_Plan_Comp = @Non_Eq_Incentive_Plan_Comp,          
     Chg_PensionValue_NQDC_Earnings = @Chg_PensionValue_NQDC_Earnings,          
     All_Other = @All_Other,          
     Total = @Total,          
     LastUpdateDate = getdate(),          
     LastUpdatedBy = ISNULL(@UserID,'CLIC')          
   WHERE   ID = @ID      
  END        
  ELSE          
  BEGIN    
   INSERT INTO wk_SummaryComp           
   (          
    Scan_ID,           
    Last_Officer_ID,           
    TagName,           
    OfficerName,           
    Company_ID,           
    FiscalYear,           
    Salary,           
    Bonus,           
    Stock_Award,           
    Option_Awards,           
    Non_Eq_Incentive_Plan_Comp,           
    Chg_PensionValue_NQDC_Earnings,           
    All_Other,           
    Total,           
    CreatedBy,           
    LastUpdatedBy          
   )          
   VALUES          
   (          
    @Scan_ID,          
    @Last_Officer_ID,          
    @TagName,          
    @OfficerName,          
    @Company_ID,          
    @FiscalYear,          
    @Salary,          
    @Bonus,          
    @Stock_Award,          
    @Option_Awards,          
    @Non_Eq_Incentive_Plan_Comp,          
    @Chg_PensionValue_NQDC_Earnings,          
    @All_Other,          
    @Total,          
    @UserID,          
    @UserID          
   );          
   SET @New_wk_ID = SCOPE_IDENTITY();        
  END      
  --SELECT @New_wk_ID;          
 END          
 -- Always check if the officer row already exists for the Officer name in the current Fiscal year. Check using name.          
 -- If so, update the wk table and @Officer_ID          
 -- @Officer_ID will be used in the IF logic below to determine Officer updates/inserts.          
 BEGIN         
  IF ISNULL(@ID,0) = 0          
   BEGIN    -- New wk row          
    SELECT @Cur_Officer_ID = ISNULL((SELECT o.Officer_ID           
      FROM wk_SummaryComp wk           
      JOIN Officer o ON wk.Company_ID = o.Company_ID           
      AND wk.FiscalYear = o.FiscalYear           
      AND REPLACE(REPLACE(wk.OfficerName, ' ', ''),'-','') = REPLACE(REPLACE(o.OfficerName, ' ', ''),'-','')--rtrim(wk.OfficerName) = rtrim(o.OfficerName)          
      WHERE wk.ID=@New_wk_ID),0);          
     UPDATE dbo.wk_SummaryComp          
     SET Officer_ID = @Cur_Officer_ID,           
      @Officer_ID = @Cur_Officer_ID          
     WHERE ID=@New_wk_ID;          
   END          
  ELSE     -- Existing wk row          
   BEGIN          
    SELECT @Cur_Officer_ID = ISNULL((SELECT o.Officer_ID           
      FROM wk_SummaryComp wk           
      JOIN Officer o ON wk.Company_ID = o.Company_ID           
      AND wk.FiscalYear = o.FiscalYear           
      AND REPLACE(REPLACE(wk.OfficerName, ' ', ''),'-','') = REPLACE(REPLACE(o.OfficerName, ' ', ''),'-','')--rtrim(wk.OfficerName) = rtrim(o.OfficerName)    
      WHERE wk.ID=@ID),0);          
    UPDATE dbo.wk_SummaryComp          
    SET Officer_ID = @Cur_Officer_ID,           
    @Officer_ID = @Cur_Officer_ID          
    WHERE ID=@ID;          
   END          
 END          
 --Update or Insert into Officer depending if Officer ID was set.          
    IF ISNULL(@Officer_ID, 0) = 0 AND ISNULL(@Last_Officer_ID, 0) = 0 -- New Officer, not in Last Fiscal Year         
  BEGIN        
  DECLARE @roleID1 INT;    
  SET @roleID1 = ISNULL((SELECT Role_ID1 FROM wk_SummaryComp wk WHERE ID = @ID),14);        
   INSERT  INTO dbo.Officer          
                    (          
                      Company_ID,          
                      FiscalYear,          
                      OfficerName,          
                      SC_Tag,          
       Salary,          
                      Bonus,          
                      Stock_Award,          
                      Option_Awards,          
                      Non_Eq_Incentive_Plan_Comp,          
                      Chg_PensionValue_NQDC_Earnings,          
                      All_Other,          
                      Role_ID1,          
                      Scan_ID,          
                      CreatedBy,          
       LastUpdatedBy,    
       Age,          
                      Year_Hired,          
                      Year_Hired_Final    
     )          
            VALUES  (          
                      @Company_ID,          
                      @FiscalYear,          
                      @OfficerName,          
                      @TagName,          
                      @Salary,          
                      @Bonus,          
                      @Stock_Award,          
                      @Option_Awards,          
                      @Non_Eq_Incentive_Plan_Comp,          
                      @Chg_PensionValue_NQDC_Earnings,          
                      @All_Other,          
                      @roleID1,          
                      @Scan_ID,          
                      ISNULL(@UserID,'CLICNew'),          
                      ISNULL(@UserID,'CLICNew'),    
       (SELECT Age FROM Officer WHERE Officer_ID = @Prev_Officer_ID) + 1,          
       (SELECT Year_Hired FROM Officer WHERE Officer_ID = @Prev_Officer_ID),          
       (SELECT Year_Hired_Final FROM Officer WHERE Officer_ID = @Prev_Officer_ID)          
     )           
   SET @New_Officer_ID = SCOPE_IDENTITY();          
   SELECT @New_Officer_ID;           
   BEGIN           
    IF @ID = 0   -- We inserted a new wk_SummaryComp Row, so we have to use the ID we obtained from the Insert        
    BEGIN       
      UPDATE dbo.wk_SummaryComp          
      SET Officer_ID = @New_Officer_ID  -- LastUpdate cols were set in previous update, don't have to update again in this run          
      WHERE ID=@New_wk_ID          
    END    
    ELSE           
    BEGIN    
      UPDATE dbo.wk_SummaryComp          
      SET Officer_ID = @New_Officer_ID  -- LastUpdate cols were set in previous update, don't have to update again in this run          
      WHERE ID=@ID             
    END    
   END          
   EXEC dbo.sp_Officer_PayRank_U @Company_ID, @FiscalYear;          
  END          
    ELSE      
  BEGIN    
   IF ISNULL(@Officer_ID, 0) = 0 -- Officer_ID is 0, Last_Officer_ID <>0, so Copy Last Year Officer forward to new year       
    BEGIN     
     SET NOCOUNT ON;          
     INSERT  INTO dbo.Officer    
     (          
                    Company_ID,          
                    FiscalYear,          
                    OfficerName,          
                    SC_Tag,          
                    Salary,          
                    Bonus,          
                    Stock_Award,          
                    Option_Awards,        
                    Non_Eq_Incentive_Plan_Comp,          
                    Chg_PensionValue_NQDC_Earnings,          
                    All_Other,          
                    Company_Title,          
                    Age,          
                    Year_Hired,          
                    Year_Hired_Final,          
                    Founder,          
                    Director,          
                    CEO_Start_Date,          
                    Role_ID1,          
                    Role_ID2,          
                    Role_ID3,          
                Role_ID4,          
                    Role_ID5,          
                    PP_Company_Title,          
                    PP_Role_ID1,          
                    PP_Role_ID2,          
                    PP_Role_ID3,          
                    PP_Role_ID4,          
                    PP_Role_ID5,          
                    Officer_PartialYear,   -- Exec Bio Notes          
                    Scan_ID,          
                    CreatedBy,          
                    LastUpdatedBy          
     )          
                    SELECT @Company_ID,          
                    @FiscalYear,          
                    @OfficerName,          
                    @TagName,          
                    @Salary,          
                    @Bonus,          
                    @Stock_Award,          
                    @Option_Awards,          
                    @Non_Eq_Incentive_Plan_Comp,          
                    @Chg_PensionValue_NQDC_Earnings,          
                    @All_Other,          
                    Company_Title,          
                    [Age]+1,          
     Year_Hired,          
     Year_Hired_Final,          
     Founder,          
     Director,          
     CEO_Start_Date,          
     CASE ISNULL(Role_ID1_Former,0) WHEN 0 THEN Role_ID1 ELSE 14 END,          
     CASE ISNULL(Role_ID2_Former,0) WHEN 0 THEN Role_ID2 ELSE NULL END,          
     CASE ISNULL(Role_ID3_Former,0) WHEN 0 THEN Role_ID3 ELSE NULL END,          
     CASE ISNULL(Role_ID4_Former,0) WHEN 0 THEN Role_ID4 ELSE NULL END,          
     CASE ISNULL(Role_ID5_Former,0) WHEN 0 THEN Role_ID5 ELSE NULL END,          
     Company_Title,          
     CASE ISNULL(PP_Role_ID1_Former,0) WHEN 0 THEN PP_Role_ID1 ELSE 14 END,          
     CASE ISNULL(PP_Role_ID2_Former,0) WHEN 0 THEN PP_Role_ID2 ELSE NULL END,          
     CASE ISNULL(PP_Role_ID3_Former,0) WHEN 0 THEN PP_Role_ID3 ELSE NULL END,          
     CASE ISNULL(PP_Role_ID4_Former,0) WHEN 0 THEN PP_Role_ID4 ELSE NULL END,          
     CASE ISNULL(PP_Role_ID5_Former,0) WHEN 0 THEN PP_Role_ID5 ELSE NULL END,          
     Officer_PartialYear,   -- Exec Bio Notes          
     @Scan_ID,          
     ISNULL(@UserID,'CLICCopyFwd'),          
     ISNULL(@UserID,'CLICCopyFwd')          
                    FROM    dbo.Officer          
                    WHERE   Officer_ID = @Last_Officer_ID;          
     SET @New_Officer_ID = SCOPE_IDENTITY();          
     SELECT @New_Officer_ID;           
        UPDATE dbo.wk_SummaryComp          
        SET Officer_ID = @New_Officer_ID          
        WHERE ID=@ID;          
     EXEC dbo.sp_Officer_PayRank_U @Company_ID, @FiscalYear;          
                END          
            ELSE -- Officer exists, so just update with new values    
    BEGIN               
     IF @Published = 0     
     BEGIN          
        UPDATE  dbo.Officer          
        SET               
       Company_ID = @Company_ID,          
       FiscalYear = @FiscalYear,          
       OfficerName = @OfficerName,          
       SC_Tag = @TagName,          
       Salary = @Salary,          
       Bonus = @Bonus,          
       Stock_Award = @Stock_Award,          
       Option_Awards = @Option_Awards,          
       Non_Eq_Incentive_Plan_Comp = @Non_Eq_Incentive_Plan_Comp,          
       Chg_PensionValue_NQDC_Earnings = @Chg_PensionValue_NQDC_Earnings,          
       All_Other = @All_Other,          
       Scan_ID = ISNULL(Scan_ID,@Scan_ID),          
       LastUpdateDate = getdate(),          
       LastUpdatedBy = 'CLICUpd'                 
        WHERE   Officer_ID = @Officer_ID;          
     END    
     ELSE     
     BEGIN          
        UPDATE  dbo.Officer          
        SET      Company_ID = @Company_ID,          
       FiscalYear = @FiscalYear,          
       OfficerName = @OfficerName,          
       Salary = @Salary,          
       Bonus = @Bonus,          
       Stock_Award = @Stock_Award,          
       Option_Awards = @Option_Awards,          
       Non_Eq_Incentive_Plan_Comp = @Non_Eq_Incentive_Plan_Comp,          
       Chg_PensionValue_NQDC_Earnings = @Chg_PensionValue_NQDC_Earnings,          
       All_Other = @All_Other,          
       SC_Tag = @TagName,          
       Scan_ID = ISNULL(Scan_ID,@Scan_ID),          
       LastUpdateDate = getdate(),          
       LastUpdatedBy = 'CLICUpd',     
       Role_ID1 = CASE  WHEN Role_ID1 IS NULL THEN (SELECT Role_ID1 FROM Officer WHERE Officer_ID = @Prev_Officer_ID) ELSE Role_ID1 END,    
       Role_ID2 =  CASE WHEN Role_ID2 IS NULL THEN (SELECT Role_ID2 FROM Officer WHERE Officer_ID = @Prev_Officer_ID) ELSE Role_ID2 END,  
       Role_ID3 =  CASE WHEN Role_ID3 IS NULL THEN (SELECT Role_ID3 FROM Officer WHERE Officer_ID = @Prev_Officer_ID) ELSE Role_ID3 END,  
       Role_ID4 =  CASE WHEN Role_ID4 IS NULL THEN (SELECT Role_ID4 FROM Officer WHERE Officer_ID = @Prev_Officer_ID) ELSE Role_ID4 END,  
       Role_ID5 = CASE WHEN Role_ID5 IS NULL THEN (SELECT Role_ID5 FROM Officer WHERE Officer_ID = @Prev_Officer_ID) ELSE Role_ID5 END,  
       Company_Title = CASE WHEN Company_Title IS NULL THEN (SELECT Company_Title FROM Officer WHERE Officer_ID = @Prev_Officer_ID) ELSE Company_Title END,  
       PP_Company_Title = CASE WHEN PP_Company_Title IS NULL THEN (SELECT PP_Company_Title FROM Officer WHERE Officer_ID = @Prev_Officer_ID) ELSE PP_Company_Title END,  
       PP_Role_ID1 = CASE WHEN PP_Role_ID1 IS NULL THEN (SELECT PP_Role_ID1 FROM Officer WHERE Officer_ID = @Prev_Officer_ID) ELSE PP_Role_ID1 END,   
       PP_Role_ID2 = CASE WHEN PP_Role_ID2 IS NULL THEN (SELECT PP_Role_ID2 FROM Officer WHERE Officer_ID = @Prev_Officer_ID) ELSE PP_Role_ID2 END,  
       PP_Role_ID3 = CASE WHEN PP_Role_ID3 IS NULL THEN (SELECT PP_Role_ID3 FROM Officer WHERE Officer_ID = @Prev_Officer_ID) ELSE PP_Role_ID3 END,  
       PP_Role_ID4 = CASE WHEN PP_Role_ID4 IS NULL THEN (SELECT PP_Role_ID4 FROM Officer WHERE Officer_ID = @Prev_Officer_ID) ELSE PP_Role_ID4 END,  
       PP_Role_ID5 = CASE WHEN PP_Role_ID5 IS NULL THEN (SELECT PP_Role_ID5 FROM Officer WHERE Officer_ID = @Prev_Officer_ID) ELSE PP_Role_ID5 END        
        WHERE   Officer_ID = @Officer_ID          
     END    
                END          
        END          
END 
```

**Behavior summary:** INSERT=True, UPDATE=True, IF-EXISTS branch=False

---

## `sp_Officer_FirstLastName_U_MAYA`

```sql
                    
                              
                                 
/*                                
 =============================================                                
-- Author:  Abhijit Deshmukh.                                
-- Create date: 09/06/2019                                
-- Description: This SPROC update the officer table.For the web Data Entry app.                                    
                                     
   Changelog :                            
   Sept, 2019 : Abhijit Deshmukh add new SPROC for MAYA project to Segregate First & Last of Executive                      
                                
======================================                                   
                                     
*/                                    
create PROCEDURE [dbo].[sp_Officer_FirstLastName_U_MAYA]                             
(                                
   @Officer_ID INT,                                
  @First_name VARCHAR(250)=NULL,                                
  @Last_name VARCHAR(250)=NULL,                                
  @Note_FirstLastName VARCHAR(250)=NULL  ,                            
  @Gender INT=NULL   ,                          
  @MasterName_ID int=NULL,                            
  @Company_ID int=NULL,                             
  @Fisical_year int=NULL,                               
  @Full_name varchar(500) = NULL,                  
  @ModifyBy varchar(max)=null                           
)                                
AS                                
BEGIN      
 declare @Role_ID1 int               
 set @Role_ID1 =(select Role_ID1 from wk_SummaryComp where Officer_ID = @Officer_ID and Company_ID = @Company_ID and FiscalYear = @Fisical_year)      
 print @Role_ID1;                        
 IF(EXISTS(SELECT 1 FROM Officer WHERE Company_ID=@Company_ID AND FiscalYear=@Fisical_year-1 and OfficerName = @Full_name))              
  BEGIN            
    
    
  IF(@Officer_ID IS NULL)  
  BEGIN  
    UPDATE            
   officer_A            
  SET            
   officer_A.First_name = officer_B.First_name,            
   officer_A.Last_name = officer_B.Last_name,            
   Note_FirstLastName=@Note_FirstLastName,           
   officer_A.Gender = officer_B.Gender,            
   officer_A.MasterNames_ID = officer_B.MasterNames_ID,            
   officer_A.Role_ID1 = @Role_ID1,            
   ModifyDate = GETDATE(),          
   ModifyBy=@ModifyBy          
  FROM            
   officer AS officer_A            
   INNER JOIN officer AS officer_B            
  ON LTRIM(RTRIM(officer_A.OfficerName))=LTRIM(RTRIM(officer_B.OfficerName)) AND officer_B.Company_ID=@Company_ID AND officer_B.FiscalYear=@Fisical_year-1             
  WHERE            
   officer_A.Company_ID=@Company_ID AND officer_A.FiscalYear=@Fisical_year AND officer_A.Role_ID1!=43            
  END  
  ELSE  
  BEGIN  
    UPDATE            
   officer_A            
  SET            
   officer_A.First_name = officer_B.First_name,            
   officer_A.Last_name = officer_B.Last_name,            
   Note_FirstLastName=@Note_FirstLastName,           
   officer_A.Gender = officer_B.Gender,            
   officer_A.MasterNames_ID = officer_B.MasterNames_ID,            
   officer_A.Role_ID1 = @Role_ID1,            
   ModifyDate = GETDATE(),          
   ModifyBy=@ModifyBy          
  FROM            
   officer AS officer_A            
   INNER JOIN officer AS officer_B            
  ON LTRIM(RTRIM(officer_A.OfficerName))=LTRIM(RTRIM(officer_B.OfficerName)) AND officer_B.Company_ID=@Company_ID AND officer_B.FiscalYear=@Fisical_year-1             
  WHERE            
   officer_A.Company_ID=@Company_ID AND officer_A.FiscalYear=@Fisical_year AND officer_A.Role_ID1!=43 AND officer_A.Officer_ID=@Officer_ID            
    
  END           
 END            
            
ELSE IF (EXISTS(select 1 from MasterNames where FullName = @Full_name and Company_ID = @Company_ID))            
 BEGIN            
            
 declare @MasterNames_ID int            
 set @MasterNames_ID = (select top 1  MasterNames_ID from MasterNames where FullName = @Full_name and Company_ID = @Company_ID order by LastFY desc)            
            
            
   UPDATE            
   officer            
  SET            
   First_name = @First_name,            
   Last_name = @Last_name,          
   Note_FirstLastName=@Note_FirstLastName,             
   Gender = @Gender,            
   MasterNames_ID = @MasterNames_ID,            
   ModifyDate = GETDATE(),          
   ModifyBy=@ModifyBy,        
   Role_ID1 = @Role_ID1         
   where Company_ID=@Company_ID AND FiscalYear=@Fisical_year AND Role_ID1!=43 AND Officer_ID = @Officer_ID             
            
 END            
            
            
ELSE            
            
 BEGIN            
  UPDATE            
   officer            
  SET            
   First_name = @First_name,            
   Last_name = @Last_name,           
   Note_FirstLastName=@Note_FirstLastName,            
   Gender = @Gender,            
   --MasterNames_ID = @MasterNames_ID,            
   ModifyDate = GETDATE(),          
   ModifyBy=@ModifyBy,       
   Role_ID1 = @Role_ID1           
   where OfficerName = @Full_name AND Company_ID=@Company_ID AND FiscalYear=@Fisical_year AND Role_ID1!=43 AND Officer_ID = @Officer_ID           
 END            
            
END       
                   
           
          
            
            
                                                                                                                                                                                                                                                      
            
                                                                                                                                                                                       

```

**Behavior summary:** INSERT=False, UPDATE=True, IF-EXISTS branch=False

---

## `sp_Officer_Roles_U_MAYA`

```sql
      
/*        
 Author: Abhijit Deshmukh         
 Created: 23/09/2019        
 Description: This SPROC updates the Summary Comp Table Roles in the Officers table for a specific officer.         
 For the web Data Entry app.        
         
          Changelog        
======================================        
 New SPROC        
 Fixed assignment of Role_ID values        
 Added CEO for IPE        
 Changed to accept -1, from Unselect choice.        
 added Company_Title  to update.     
 add new fild modifydate and modify By 
 Added age >= 70 and A_Notes_Nulling_Retirement = 'RIRR and benchmark value of retirement not calculated because NEO is over age 70.' 
 Conditions for the field 'A_Notes_Nulling_Retirement'   
 Added New field --'Officer_For_PartialYear' to reflec on UI(clickbox) for the field 'Null Retirement Values' if age is over 70.
*/     

     
CREATE PROCEDURE [dbo].[sp_Officer_Roles_U_MAYA]    
    (        
      @Officer_ID INT, 
	  @Officer_ID_py1 INT, 
	  @Officer_ID_py2 INT,  
	  @Company_ID INT,
	  @FiscalYear INT,   
	  @Full_name varchar(500) = NULL,    
              
      @Role_ID1 INT = NULL,        
      @Role_ID1_Former BIT = NULL,        
      @Role_ID2 INT = NULL,        
      @Role_ID2_Former BIT = NULL,        
      @Role_ID3 INT = NULL,        
      @Role_ID3_Former BIT = NULL,        
      @Role_ID4 INT = NULL,        
      @Role_ID4_Former BIT = NULL,        
      @Role_ID5 INT = NULL,        
      @Role_ID5_Former BIT = NULL,    
	      
      @Founder BIT = NULL,        
      @Director BIT = NULL,        
      @Interim BIT = NULL,        
      @CEO_for_IPE BIT = NULL,      
      @Company_Title nvarchar(200)=NULL ,  
      @ModifyBy varchar(max)=null      
          )        
AS         
    BEGIN          
            
           
        UPDATE  dbo.Officer        
        SET     Role_ID1 = @Role_ID1,        
                Role_ID1_Former = @Role_ID1_Former,        
                Role_ID2 = CASE @Role_ID2 WHEN -1 THEN NULL ELSE @Role_ID2 END,        
                Role_ID2_Former = CASE @Role_ID2 WHEN -1 THEN NULL ELSE @Role_ID2_Former END,        
                Role_ID3 = CASE @Role_ID3 WHEN -1 THEN NULL ELSE @Role_ID3 END,        
                Role_ID3_Former = CASE @Role_ID3 WHEN -1 THEN NULL ELSE @Role_ID3_Former END,        
                Role_ID4 = CASE @Role_ID4 WHEN -1 THEN NULL ELSE @Role_ID4 END,        
                Role_ID4_Former = CASE @Role_ID4 WHEN -1 THEN NULL ELSE @Role_ID4_Former END,        
                Role_ID5 = CASE @Role_ID5 WHEN -1 THEN NULL ELSE @Role_ID5 END,        
                Role_ID5_Former = CASE @Role_ID5 WHEN -1 THEN NULL ELSE @Role_ID5_Former END,        
                Founder = @Founder,        
                CEO_For_IPE = @CEO_for_IPE,                           
                Director = @Director,        
                Interim = @Interim ,       
                Company_Title=@Company_Title,  
                ModifyBy=@ModifyBy ,  
                ModifyDate=GETDATE()         
        WHERE   Officer_ID = @Officer_ID        
		
		 IF(EXISTS(SELECT 1 FROM Officer WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear-1 and Officer_ID = @Officer_ID_py1))  
			UPDATE  dbo.Officer
			SET		Age=(SELECT Age+1 FROM Officer WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear-1 AND Officer_ID = @Officer_ID_py1),
					Year_Hired=(SELECT Year_Hired FROM Officer WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear-1 AND Officer_ID = @Officer_ID_py1),
					Year_Hired_Final=(SELECT Year_Hired_Final FROM Officer WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear-1 AND Officer_ID = @Officer_ID_py1),
					A_Notes_Nulling_Retirement=(SELECT A_Notes_Nulling_Retirement FROM Officer WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear-1 AND Officer_ID = @Officer_ID_py1 AND Age >= 70 
								AND A_Notes_Nulling_Retirement = 'RIRR and benchmark value of retirement not calculated because NEO is over age 70.')				
			where   Officer_ID=@Officer_ID and FiscalYear=@FiscalYear

		 ELSE
			UPDATE  dbo.Officer
			SET		Age=(SELECT Age+2 FROM Officer WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear-2 AND Officer_ID = @Officer_ID_py2),
					Year_Hired=(SELECT Year_Hired FROM Officer WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear-2 AND Officer_ID = @Officer_ID_py2),
					Year_Hired_Final=(SELECT Year_Hired_Final FROM Officer WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear-2 AND Officer_ID = @Officer_ID_py2)
			where   Officer_ID=@Officer_ID and FiscalYear=@FiscalYear

		
		IF(EXISTS(SELECT 1 FROM Officer WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear AND Officer_ID = @Officer_ID AND Age >= 70
					AND A_Notes_Nulling_Retirement = 'RIRR and benchmark value of retirement not calculated because NEO is over age 70.'))
			UPDATE  dbo.Officer
			SET		Officer_For_PartialYear = 1
            where   Officer_ID=@Officer_ID and FiscalYear=@FiscalYear
			     
    END 


```

**Behavior summary:** INSERT=False, UPDATE=True, IF-EXISTS branch=False

---

## `sp_Officer_PerfPeriod_Roles_U_MAYA`

```sql
/*        
 Author: Abhijit Deshmukh         
 Created: 23/09/2019        
 Description: This SPROC updates the Summary Comp Table Performance Period Roles in the  Officers table for a specific officer.         
 For the web Data Entry app.        
         
          Changelog        
======================================        
 New SPROC        
 Fixed assignment of Role_ID values        
 Added CEO for IPE        
 Changed to accept -1, from Unselect choice.        
 added Company_Title  to update.     
 add new fild modifydate and modify By          
*/         


CREATE PROCEDURE [dbo].[sp_Officer_PerfPeriod_Roles_U_MAYA]  
    (    
      @Officer_ID INT, 
	  @Officer_ID_py1 INT, 
	  @Officer_ID_py2 INT,  
	  @Company_ID INT,
	  @FiscalYear INT,
	  @Full_name varchar(500) = NULL, 
	       
      @PP_Role_ID1 INT = NULL,    
      @PP_Role_ID1_Former BIT = NULL,    
      @PP_Role_ID2 INT = NULL,    
      @PP_Role_ID2_Former BIT = NULL,    
      @PP_Role_ID3 INT = NULL,    
      @PP_Role_ID3_Former BIT = NULL,    
      @PP_Role_ID4 INT = NULL,    
      @PP_Role_ID4_Former BIT = NULL,    
      @PP_Role_ID5 INT = NULL,    
      @PP_Role_ID5_Former BIT = NULL, 
	     
      @CEO_Start_Date Datetime = NULL,      
      @Curr_Position_EndDt Datetime = NULL,     
      @Position_Changed BIT = NULL  , 
	  @Interim BIT = NULL,  
	  @PP_Company_Title VARCHAR(200) = NULL,
	  @ModifyBy varchar(max)=null 

    )    
AS     
    BEGIN    
      
     
        UPDATE  dbo.Officer    
        SET     PP_Company_Title = @PP_Company_Title,    
				PP_Role_ID1 = CASE @PP_Role_ID1 WHEN -1 THEN NULL ELSE @PP_Role_ID1 END,    
				PP_Role_ID1_Former = @PP_Role_ID1_Former,    
				PP_Role_ID2 = CASE @PP_Role_ID2 WHEN -1 THEN NULL ELSE @PP_Role_ID2 END,    
				PP_Role_ID2_Former = @PP_Role_ID2_Former,    
				PP_Role_ID3 = CASE @PP_Role_ID3 WHEN -1 THEN NULL ELSE @PP_Role_ID3 END,    
				PP_Role_ID3_Former = @PP_Role_ID3_Former,    
				PP_Role_ID4 = CASE @PP_Role_ID4 WHEN -1 THEN NULL ELSE @PP_Role_ID4 END,    
				PP_Role_ID4_Former = @PP_Role_ID4_Former,    
				PP_Role_ID5 = CASE @PP_Role_ID5 WHEN -1 THEN NULL ELSE @PP_Role_ID5 END,    
				PP_Role_ID5_Former = @PP_Role_ID5_Former,    
				CEO_Start_Date = @CEO_Start_Date,    
				Curr_Position_EndDt = @Curr_Position_EndDt,    
				Position_Changed = @Position_Changed  ,  
				ModifyBy=@ModifyBy ,  
				ModifyDate=GETDATE()      
		WHERE   Officer_ID = @Officer_ID    


		 IF(EXISTS(SELECT 1 FROM Officer WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear-1 and Officer_ID = @Officer_ID_py1))  
			UPDATE  dbo.Officer
			SET		CEO_Start_Date=(SELECT CEO_Start_Date FROM Officer WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear-1 AND Officer_ID = @Officer_ID_py1)
			where   Officer_ID=@Officer_ID and FiscalYear=@FiscalYear

		 ELSE 
			UPDATE  dbo.Officer
			SET		CEO_Start_Date=(SELECT CEO_Start_Date FROM Officer WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear-2 AND Officer_ID = @Officer_ID_py2)
			where   Officer_ID=@Officer_ID and FiscalYear=@FiscalYear
         
    END    

```

**Behavior summary:** INSERT=False, UPDATE=True, IF-EXISTS branch=False

---

## `sp_Tracking_Data_Entry_U_MAYA`

```sql
      
      
      
          
/*                                      
 Author: Abhijit Deshmukh                                      
 Created: 03/09/2019                                      
 Description: This is a callable SPROC to be used by web form buttons to Update a row in Tracking_Data_Entry.                                       
  Pass in the Data Group, the Status (Parsing, DataEntry, PeerCheck, FinalCheck) and the form will perform the proper update.                                      
  Validation may be called from here.                                      
  For the web Data Entry app.                                      
  Parameters:                                       
  @Status = Parsing, DataEntry, PeerCheck, FinalCheck                                      
  @DataGroup = SCT, PBA, Officer                                      
          Changelog                                      
======================================                                      
                                    
 Added updates for Tracking and Publisher comments.                                      
 Fixed setting of bit flag for PBA on FinalCheck. Was setting into comment column.                                      
 Added updates for Tracking and Publisher comments of EarlyReleaseInput and EarlyReleasePeer status.                                    
 Updated the Officer's table for QA_Off_Info columns                              
 Updated the table 'Tracking_Data_Entry' now Final review will be saved into Tracking_Data_Entry in place of table 'Publisher_Tracking'                               
 Added @DataEntryNote_Comment to Update DataEntryNote_Comment column.                          
 Added @DataGroup='BOD' if statement to Update in DataEntry,PeerCheck and FinalCheck data.                          
 Added @DataGroup='AGMDetails' if statement to Update in DataEntry,PeerCheck and FinalCheck data.                         
 Added @DataGroup='GovEquityProposal' if statement to Update in DataEntry,PeerCheck and FinalCheck data.                         
 Added @DataGroup='SeveranceCIC' if statement to Update in DataEntry,PeerCheck and FinalCheck data.                         
 Added @DataGroup='CDA' if statement to Update in DataEntry,PeerCheck and FinalCheck data.                         
 Added in @DataGroup='CDA' PeerCheck if statement columns Sweeper_NEIP_ChangeInPension,Sweeper_NEIP_ChangeInPension_Name                  
 ,Sweeper_NEIP_ChangeInPension_Dt,QA_Sweeper_NEIP_ChangeInPension                 
 Added Added for @DataGroup='BOD' - @Status: PeerCheck & DataEntry Data E if statement columns Board_Pay_Reviewed,Board_Pay_Name,Board_Pay_Dt,QA_Board_Pay_Reviewed               
 Updated Off_Info_Reviewed - for Officer's tracking              
 Added the login to insert a row in Tracking_Data_Entry, when company is getting processed 1st by BOD Section (under - DataEntry).              
 Added @DataGroup='CEOPayRatio' if statement to Update in DataEntry,PeerCheck and FinalCheck data.            
 Added @DataGroup='Financials' if statement to Update in DataEntry,PeerCheck, FinalCheck, EarlyReleaseInput and EarlyReleasePeer  data.            
 Added Financials_Post_Parsed under "Peer review" for Financials tab.         
 added @DataGroup='GenderPayEquity' if statement to Update in DataEntry,PeerCheck and FinalCheck  data.        
 Added @DataGroup='Retirement' if statement to Update in DataEntry,PeerCheck, FinalCheck data.       
 Added  @DataGroup='Section3' if statement to Update in DataEntry,PeerCheck, FinalCheck data.         
*/   
                                   
CREATE PROCEDURE [dbo].[sp_Tracking_Data_Entry_U_MAYA]                                      
    (                                      
      @Company_ID INT,                                      
      @FiscalYear INT,                      
      @DataGroup NVARCHAR(50),            
      @Status NVARCHAR(50),                                      
      @DataEntryNote_Comment NVARCHAR(250) = NULL,                  
      @Peer_Comment NVARCHAR(250) = NULL,                                      
      @Final_Comment NVARCHAR(250) = NULL,                          
      @UserID NVARCHAR(50) = NULL,          
      @Result NVARCHAR(500) OUT                                      
    )                                      
AS                                       
BEGIN                                      
 DECLARE @Validation AS NVARCHAR(500);                                      
 BEGIN                                      
-- Always set the comments from the form. Set the appropriate comments based on the form that called this SPROC.                                      
-- DataGroup is the parameter that identifies the calling form.                                      
  IF @DataGroup='SCT'                                      
   BEGIN                                      
    UPDATE Tracking_Data_Entry                                      
 SET QA_Sweeper_Perquisites = @Peer_Comment                                      
    WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
    UPDATE Tracking_Data_Entry                                      
    SET PT_QA_Perquisites = @Final_Comment                                      
    WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
   END                                      
  ELSE IF @DataGroup='PBA'                                      
   BEGIN                                      
    UPDATE Tracking_Data_Entry                                      
    SET QA_Sweeper_Plan_Based = @Peer_Comment                                      
    WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
    UPDATE Tracking_Data_Entry                                      
    SET PT_QA_Plan_Based_Awards_Metrics_Vesting = @Final_Comment                                      
    WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
 END                                      
  ELSE IF @DataGroup='Officer'                                      
   BEGIN                                      
    UPDATE Tracking_Data_Entry                                      
    SET QA_Off_Info = @Peer_Comment                                      
    WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
    UPDATE Tracking_Data_Entry                                      
    SET PT_QA_Off_Info = @Final_Comment                               
    WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
   END                                      
 END                                      
    IF ISNULL(@Status, '') = ''                                      
  SET @Result = 'Status parameter was not provided'                                      
 ELSE IF ISNULL(@DataGroup,'') = ''                                      
  SET @Result = 'Data Group parameter was not provided'                                      
    ELSE IF ISNULL(@UserID,'')=''                                       
  SET @Result = 'User ID parameter was not provided'                                      
 ELSE                                       
  BEGIN                                      
   SET @Validation = ''                                      
   IF @Validation <> ''                                      
    SET @Result = 'Validation failed: ' + @Validation                                      
   ELSE        
    IF @Status = 'Parsing'                                      
     BEGIN                                      
      UPDATE dbo.Tracking_Data_Entry               
      SET Parsing_Entered=1, Parsing_Entered_Dt=GETDATE(), Parsing_Entered_Name=@UserID                    
      WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
      SET @Result = '';                                      
     END                                      
    ELSE IF @Status='DataEntry'                                      
     BEGIN                    
      IF @DataGroup = 'SCT'                                      
       BEGIN                                      
        UPDATE dbo.Tracking_Data_Entry                                       
        SET Parsing_Entered=1,                                       
         Parsing_Entered_Dt=GETDATE(),                           
         Parsing_Entered_Name=@UserID,                                      
         Perquisites_entered=1,                                      
         Perquisites_entered_Dt=GETDATE(),                                      
         Perquisites_entered_Name=@UserID                                      
   WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';                                      
       END                           
       ELSE IF @DataGroup='BOD'                          
       BEGIN                  
    if (select COUNT(*) from Tracking_Data_Entry where Company_ID=@Company_ID AND FiscalYear=@FiscalYear) <1               
     BEGIN              
     INSERT into dbo.Tracking_Data_Entry (Company_ID, FiscalYear) VALUES (@Company_ID,@FiscalYear)              
     SET @Result = '';                 
     END              
    ELSE              
     BEGIN              
   UPDATE dbo.Tracking_Data_Entry                          
    SET BoardPay_entered_Dt=GETDATE(),                          
    BoardPay_entered_Name =@UserID,                          
    DataEntryNote_BoardPay=@DataEntryNote_Comment ,              
    Board_Pay=1,              
    Board_Pay_Name=@UserID,              
    Board_Pay_Dt=GETDATE()              
    WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                          
    SET @Result = '';                 
     END              
                              
       END                                     
      ELSE IF @DataGroup = 'PBA'                                      
       BEGIN                                      
        UPDATE dbo.Tracking_Data_Entry                                       
        SET Plan_Based_Awards_Post_Parsed = 1,                                       
         Plan_Based_Awards_Post_Parsed_Dt=GETDATE(),                                      
         Plan_Based_Awards_Post_Parsed_Name=@UserID                                      
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';                                      
       END                                      
      ELSE IF @DataGroup = 'Officer'                                      
       BEGIN                                      
   UPDATE dbo.Tracking_Data_Entry                                       
        SET               
        Off_Info_Reviewed=1, --Off_Info_Checked = 1,         Comment by Ajit K. on 19th June,17                              
         Off_Info_Reviewed_Dt = GETDATE(),                                      
         Off_Info_Reviewed_Name=@UserID                                      
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';                                      
       END                                  
    ELSE IF @DataGroup = 'CompanyPeers'                                      
       BEGIN     
        UPDATE dbo.Tracking_Data_Entry                                       
SET Peers_Entered = 1,                                       
         Peers_Entered_Dt=GETDATE(),                                      
         Peers_Entered_Name=@UserID                                      
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';                                      
       END                              
       ELSE IF @DataGroup='AGMDetails'                        
       BEGIN                        
       UPDATE Tracking_Data_Entry                        
       SET AGM_Entered_Dt=GETDATE(),                        
           AGM_Entered_Name=@UserID                        
       WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;             
       SET @Result = '';                             
       END           
             
        ELSE IF @DataGroup='GenderPayEquity'                        
       BEGIN                        
       UPDATE Tracking_Data_Entry                        
       SET       
          GenderPayEquity_Entered = 1,       
          GenderPayEquity_Entered_Dt=GETDATE(),                        
           GenderPayEquity_Entered_Name=@UserID                        
       WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                         
       SET @Result = '';                             
       END       
                           
       ELSE IF @DataGroup='GovEquityProposal'                        
       BEGIN                        
        UPDATE Tracking_Data_Entry                        
        SET                        
           Gov_Eq_Pro_Entered_Dt=GETDATE(),                        
           Gov_Eq_Pro_Entered_Name=@UserID                        
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                         
        SET @Result = '';                            
       END             
       ELSE IF @DataGroup='CEOPayRatio'                        
       BEGIN                        
        UPDATE Tracking_Data_Entry                        
        SET                    
           CEO_Pay_Ratio_Entered=1,                
           CEO_Pay_Ratio_Entered_Dt=GETDATE(),                        
           CEO_Pay_Ratio_Entered_Name=@UserID                        
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                         
        SET @Result = '';                            
       END                            
       ELSE IF @DataGroup='SeveranceCIC'                        
       BEGIN                        
        UPDATE Tracking_Data_Entry                        
        SET                        
           Sev_CIC_Entered_Dt=GETDATE(),                        
           Sev_CIC_Entered_Name=@UserID                        
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                         
        SET @Result = '';                                 
       END            
                 
       ELSE IF @DataGroup='Financials'                        
       BEGIN                        
        UPDATE Tracking_Data_Entry                        
        SET                        
        Co_Fin_Off_Info_Entered=1,          
  Co_Fin_Off_Info_Entered_Dt=GETDATE(),          
  Co_Fin_Off_Info_Entered_Name=@UserID          
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                         
        SET @Result = '';                                 
       END            
                             
       ELSE IF @DataGroup='CDA'                             
       BEGIN                      
        UPDATE Tracking_Data_Entry                      
        SET                      
            Proxy_Info_Entered=1,                      
   Proxy_Info_Entered_Dt=GETDATE(),                      
   Proxy_Info_Entered_Name=@UserID              
  WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                         
        SET @Result = '';                        
       END     
       ELSE IF @DataGroup='Section3'                             
       BEGIN                      
        UPDATE Tracking_Data_Entry                      
        SET                      
     Section3_Entered_Dt=GETDATE(),                      
     Section3_Entered_Name=@UserID                      
    WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                         
        SET @Result = '';                        
       END     
       ELSE IF @DataGroup='Retirement'                               
       BEGIN                        
        UPDATE Tracking_Data_Entry                        
        SET                        
            Retirement_Plans_Entered=1,                        
   Retirement_Plans_Entered_Dt=GETDATE(),                        
   Retirement_Plans_Entered_Name=@UserID                        
   WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                    
   SET @Result = '';                       
       END                             
        ELSE IF @DataGroup='CorporateFinancials'                    
                    
    BEGIN                  
    if (select COUNT(*) from Tracking_Data_Entry where Company_ID=@Company_ID AND FiscalYear=@FiscalYear) <1               
     BEGIN              
     INSERT into dbo.Tracking_Data_Entry (Company_ID, FiscalYear) VALUES (@Company_ID,@FiscalYear)              
     SET @Result = '';                 
     END              
    ELSE              
         BEGIN              
              
          UPDATE Tracking_Data_Entry                    
          SET                    
             Corporate_Financials_Entered_Dt=GETDATE(),                    
             Corporate_Financials_Entered_Name=@UserID                    
          WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                         
             SET @Result = '';                        
       END                   
   END                             
      ELSE                       
       SET @Result = 'Invalid Data Group provided.'           
     END                                       
    ELSE IF @Status = 'PeerCheck'                                      
     BEGIN                                      
      IF @DataGroup='SCT'                                      
       BEGIN                                      
        UPDATE dbo.Tracking_Data_Entry                                       
        SET Sweeper_Perquisites=1,                                      
         Sweeper_Perquisites_Dt=GETDATE(),                                      
         Sweeper_Perquisites_Name=@UserID   ,                
          Sweeper_NEIP_ChangeInPension=1,                  
   Sweeper_NEIP_ChangeInPension_Name=@UserID,                  
   Sweeper_NEIP_ChangeInPension_Dt=GETDATE(),                  
   QA_Sweeper_NEIP_ChangeInPension=@Peer_Comment                  
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';                                      
       END                                
       ELSE IF @DataGroup='BOD'                          
       BEGIN                          
          UPDATE dbo.Tracking_Data_Entry               
         SET Sweeper_BoardPay_Dt=GETDATE(),                          
         Sweeper_BoardPay_Name =@UserID,                          
         QA_Sweeper_BoardPay=@Peer_Comment,              
          Board_Pay_Reviewed=1,              
          Board_Pay_Reviewed_Name =@UserID,              
          Board_Pay_Reviewed_Dt  =GETDATE(),              
          QA_Board_Pay_Reviewed=@Peer_Comment                                
         WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                          
         SET @Result = '';                          
       END                          
      ELSE IF @DataGroup = 'PBA'           
      BEGIN                                      
        UPDATE dbo.Tracking_Data_Entry                                       
        SET Sweeper_Plan_Based=1,                                      
         Sweeper_Plan_Based_Dt=GETDATE(),                           
         Sweeper_Plan_Based_Name=@UserID                                      
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';                                      
       END                                
      ELSE IF @DataGroup = 'Officer'                                      
       BEGIN                                      
        UPDATE dbo.Tracking_Data_Entry                                       
        SET Off_Info_Checked =1,                                
        QA_Off_Info_Dt=GETDATE(),                                      
         QA_Off_Info_By=@UserID                                      
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';                                      
       END              
    ELSE IF @DataGroup = 'CompanyPeers'                                      
       BEGIN                                      
        UPDATE dbo.Tracking_Data_Entry                                       
        SET QA_Peers =1,                              
        QA_Peers_Dt=GETDATE(),                                      
         QA_Peers_By=@UserID                                      
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';                                      
       END                               
      ELSE IF @DataGroup='AGMDetails'                        
      BEGIN                        
       UPDATE Tracking_Data_Entry                        
       SET                        
          Sweeper_AGM_Dt=GETDATE(),                        
          Sweeper_AGM_Name=@UserID,                        
          QA_Sweeper_AGM=@Peer_Comment                        
       WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
       SET @Result = '';                         
      END        
            
        ELSE IF @DataGroup='GenderPayEquity'                        
      BEGIN                        
       UPDATE Tracking_Data_Entry                        
       SET                        
          Sweeper_GenderpayEquity_Dt=GETDATE(),                        
          Sweeper_GenderpayEquity_Name=@UserID,                        
          QA_Sweeper_GenderpayEquity=@Peer_Comment                        
       WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
       SET @Result = '';                         
      END                        
                              
      ELSE IF @DataGroup='GovEquityProposal'                        
      BEGIN                        
       UPDATE Tracking_Data_Entry                        
       SET                        
         Sweeper_Gov_Eq_Pro_Dt=GETDATE(),                        
         Sweeper_Gov_Eq_Pro_Name=@UserID,                        
         QA_Sweeper_Gov_Eq_Pro=@Peer_Comment                        
       WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
       SET @Result = '';                          
      END               
      ELSE IF @DataGroup='CEOPayRatio'                        
      BEGIN                        
       UPDATE Tracking_Data_Entry                        
       SET               
         Sweeper_CEO_Pay_Ratio_Dt=GETDATE(),                        
         Sweeper_CEO_Pay_Ratio_Name=@UserID,                        
         QA_Sweeper_CEO_Pay_Ratio=@Peer_Comment                        
       WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;   
       SET @Result = '';                          
      END                              
      ELSE IF @DataGroup='SeveranceCIC'                        
      BEGIN                        
        UPDATE Tracking_Data_Entry                        
        SET                        
   Sweeper_Sev_CIC_Dt=GETDATE(),                        
   Sweeper_Sev_CIC_Name=@UserID,                        
   QA_Sweeper_Sev_CIC=@Peer_Comment                        
    WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
       SET @Result = '';                         
      END           
      ELSE IF @DataGroup='Financials'                        
      BEGIN                        
        UPDATE Tracking_Data_Entry                        
        SET              
       Financials_Post_Parsed=1,                
   QA_Co_Fin_Off_Info_Dt=GETDATE(),                        
   QA_Co_Fin_Off_Info_By=@UserID,                        
   QA_Co_Fin_Off_Info=@Peer_Comment                        
    WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
       SET @Result = '';                         
      END           
                            
      ELSE IF @DataGroup='CDA'                      
      BEGIN                      
        UPDATE Tracking_Data_Entry                      
        SET                      
            Sweeper_Proxy_Info_and_SayOnPay=1,                      
   Sweeper_Proxy_Info_and_SayOnPay_Dt=GETDATE(),                       
   Sweeper_Proxy_Info_and_SayOnPay_Name=@UserID,                      
   QA_Sweeper_Proxy_Info_and_SayOnPay=@Peer_Comment                  
         WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
       SET @Result = '';                      
      END       
          
       ELSE IF @DataGroup='Retirement'                        
      BEGIN                        
        UPDATE Tracking_Data_Entry                        
        SET                        
            Retirement_Plans_Reviewed=1,                        
   Retirement_Plans_Reviewed_Dt=GETDATE(),                         
   Retirement_Plans_Reviewed_Name=@UserID,                        
   QA_Ret_Plans_Reviewed=@Peer_Comment                    
         WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                        
       SET @Result = '';                        
      END           
                         
      ELSE IF @DataGroup='CorporateFinancials'                    
      BEGIN                    
         UPDATE Tracking_Data_Entry                    
         SET                    
           Sweeper_Corporate_Financials_Dt=GETDATE(),                    
           Sweeper_Corporate_Financials_Name=@UserID,                    
           QA_Sweepe_Corporate_Financials=@Peer_Comment                    
         WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
       SET @Result = '';                       
      END      
      ELSE IF @DataGroup='Section3'                    
      BEGIN                    
         UPDATE Tracking_Data_Entry                    
         SET                    
           Sweeper_Section3_Dt=GETDATE(),                    
           Sweeper_Section3_Name=@UserID,                    
           QA_Sweeper_Section3=@Peer_Comment                    
         WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
       SET @Result = '';                      
      END                        
      ELSE                                      
       SET @Result = ''                                      
     END                                      
    ELSE IF @Status = 'FinalCheck'                                      
     BEGIN           
      IF @DataGroup='SCT'                                      
       BEGIN                                      
        UPDATE dbo.Tracking_Data_Entry                              
        SET PT_Perquisites=1,                                      
         PT_QA_Perquisites_Dt=GETDATE(),                                      
         PT_QA_Perquisites_By=@UserID                                      
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';                                      
         exec sp_PriorityReleaseDt @Company_ID,@FiscalYear                                  
       END                             
       ELSE IF @DataGroup='BOD'                          
       BEGIN                          
         UPDATE dbo.Tracking_Data_Entry                          
         SET PT_QA_BoardPay_Dt=GETDATE(),                          
         PT_QA_BoardPay_By =@UserID,                          
         PT_QA_BoardPay=@Final_Comment                                   
         WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                          
         SET @Result = '';                          
       END                                   
      ELSE IF @DataGroup = 'PBA'                                      
       BEGIN                                      
        UPDATE dbo.Tracking_Data_Entry                                      
        SET PT_Plan_Based_Awards_Metrics_Vesting=1,                                   
         PT_QA_Plan_Based_Awards_Metrics_Vesting_Dt=GETDATE(),                                      
         PT_QA_Plan_Based_Awards_Metrics_Vesting_By=@UserID                                      
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';                                     
         exec sp_PriorityReleaseDt @Company_ID,@FiscalYear                                   
       END                                      
      ELSE IF @DataGroup = 'Officer'                                      
       BEGIN                                      
        UPDATE dbo.Tracking_Data_Entry                                      
        SET PT_Off_Info=1,                                      
         PT_QA_Off_Info_Dt=GETDATE(),                                      
         PT_QA_Off_Info_By=@UserID                                      
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';                                      
         exec sp_PriorityReleaseDt @Company_ID,@FiscalYear                                          
       END                          
       ELSE IF @DataGroup='AGMDetails'                        
       BEGIN                        
        UPDATE Tracking_Data_Entry                        
        SET                        
   PT_QA_AGM_Dt=GETDATE(),                        
   PT_QA_AGM_By=@UserID,                        
   PT_QA_AGM=@Final_Comment                        
      WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                          
        SET @Result = '';                         
       END           
             
        ELSE IF @DataGroup='GenderPayEquity'                        
       BEGIN                        
        UPDATE Tracking_Data_Entry                        
        SET                        
   PT_QA_GenderpayEquity_Dt=GETDATE(),                        
   PT_QA_GenderpayEquity_By=@UserID,                     
   PT_QA_GenderpayEquity=@Final_Comment                        
      WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                          
        SET @Result = '';                         
       END          
             
                                 
       ELSE IF @DataGroup='GovEquityProposal'                        
       BEGIN                        
        UPDATE Tracking_Data_Entry                        
        SET                        
          PT_QA_Gov_Eq_Pro_Dt=GETDATE(),                        
        PT_QA_Gov_Eq_Pro_By=@UserID,                        
          PT_QA_Gov_Eq_Pro=@Final_Comment                        
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                          
        SET @Result = '';                          
       END            
       ELSE IF @DataGroup='CEOPayRatio'            
       BEGIN            
         UPDATE Tracking_Data_Entry                        
        SET                        
          PT_QA_CEO_Pay_Ratio_Dt=GETDATE(),                        
          PT_QA_CEO_Pay_Ratio_By=@UserID,                        
          PT_QA_CEO_Pay_Ratio=@Final_Comment                        
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                          
        SET @Result = '';               
       END                        
       ELSE IF @DataGroup='SeveranceCIC'                        
       BEGIN                        
       UPDATE Tracking_Data_Entry                        
       SET                        
          PT_QA_Sev_CIC_Dt=GETDATE(),                        
          PT_QA_Sev_CIC_By=@UserID,                        
          PT_QA_Sev_CIC=@Final_Comment                        
       WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                          
       SET @Result = '';                            
       END               
       ELSE IF @DataGroup='Financials'                        
       BEGIN                        
       UPDATE Tracking_Data_Entry                        
       SET                        
          PT_QA_Co_Fin_Off_Info_Dt=GETDATE(),                        
          PT_QA_Co_Fin_Off_Info_By=@UserID,                        
          PT_QA_Co_Fin_Off_Info=@Final_Comment                        
       WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                          
       SET @Result = '';                            
       END                        
       ELSE IF @DataGroup='CDA'                      
       BEGIN                      
        UPDATE Tracking_Data_Entry                      
        SET                     
          PT_CDA=1,                      
          PT_QA_CDA_Dt=GETDATE(),                      
          PT_QA_CDA_By=@UserID,                      
          PT_QA_CDA=@Final_Comment                      
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                          
       SET @Result = '';                        
       END      
           
       ELSE IF @DataGroup='Retirement'                        
       BEGIN                        
        UPDATE Tracking_Data_Entry                        
        SET                        
          PT_QA_Retirement_Plans_Dt=GETDATE(),                        
          PT_QA_Retirement_Plans_By=@UserID,                        
          PT_QA_Retirement_Plans=@Final_Comment                        
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                            
       SET @Result = '';                          
       END           
                           
       ELSE IF @DataGroup='CorporateFinancials'                    
      BEGIN                    
       UPDATE Tracking_Data_Entry                    
       SET                    
          PT_QA_Corporate_Financials_Dt=GETDATE(),                    
          PT_QA_Corporate_Financials_By=@UserID,                    
          PT_QA_Corporate_Financials=@Final_Comment                    
       WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                          
       SET @Result = '';                       
      END       
       ELSE IF @DataGroup='Section3'                    
      BEGIN                    
       UPDATE Tracking_Data_Entry                    
       SET                    
          PT_QA_Section3_Dt=GETDATE(),                    
          PT_QA_Section3_By=@UserID,                    
          PT_QA_Section3=@Final_Comment                    
       WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                          
       SET @Result = '';                       
      END                                     
      ELSE                                      
       SET @Result = ''                                      
     END                                      
    ELSE IF @Status = 'EarlyReleaseInput'                                      
     BEGIN                                      
      IF @DataGroup='SCT'                                      
   BEGIN                                      
        UPDATE Tracking_Data_Entry                                    
        SET Perquisites_Priority_Entered=1,                                      
         Perquisites_Priority_Entered_Dt=GETDATE(),                                      
      Perquisites_Priority_Entered_Name=@UserID                                      
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';                                    
         exec sp_PriorityReleaseDt @Company_ID,@FiscalYear                                    
       END                                      
       ELSE IF @DataGroup = 'PBA'                                      
       BEGIN                               
        UPDATE Tracking_Data_Entry                                      
        SET Plan_Based_Awards_Priority=1,                                      
         Plan_Based_Awards_Priority_Dt=GETDATE(),                      
         Plan_Based_Awards_Priority_Name=@UserID                                      
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';                                     
         exec sp_PriorityReleaseDt @Company_ID,@FiscalYear                                   
       END           
       ELSE IF @DataGroup = 'Financials'                                      
       BEGIN                                      
        UPDATE Tracking_Data_Entry                                      
        SET Co_Fin_Off_Info=1,                                      
         Co_Fin_Off_Info_Dt=GETDATE(),                                      
         Co_Fin_Off_Info_Name=@UserID                                      
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';                                     
         exec sp_PriorityReleaseDt @Company_ID,@FiscalYear                                   
       END                           
        ELSE IF @DataGroup='CorporateFinancials'                    
       BEGIN                    
         UPDATE Tracking_Data_Entry                    
         SET                    
           Corporate_Financials_Priority_Entered=1,                    
           Corporate_Financials_Priority_Entered_Dt=GETDATE(),                    
  Corporate_Financials_Priority_Entered_Name=@UserID                    
         WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';           
         exec sp_PriorityReleaseDt @Company_ID,@FiscalYear                       
       END                                         
      ELSE                                      
       SET @Result = ''                                      
   END                                     
    ELSE IF @Status = 'EarlyReleasePeer'                                      
     BEGIN                                      
      IF @DataGroup='SCT'                                      
       BEGIN                                      
        UPDATE Tracking_Data_Entry                                    
        SET Sweeper_Perquisites_Priority=1,                                      
         Sweeper_Perquisites_Priority_Dt=GETDATE(),                                      
         Sweeper_Perquisites_Priority_Name=@UserID                                      
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';                                      
        exec sp_PriorityReleaseDt @Company_ID,@FiscalYear                                  
       END                                      
        ELSE IF @DataGroup = 'PBA'                                      
       BEGIN                
        UPDATE Tracking_Data_Entry                                      
        SET Sweeper_Plan_Based_Priority=1,                                      
         Sweeper_Plan_Based_Priority_Dt=GETDATE(),                                      
         Sweeper_Plan_Based_Priority_Name=@UserID                                      
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';                                      
       END           
                 
       ELSE IF @DataGroup = 'Financials'                                      
       BEGIN                                      
        UPDATE Tracking_Data_Entry                                      
        SET Sweeper_Co_Fin_Off_Info=1,                                      
         Sweeper_Co_Fin_Off_Info_Dt=GETDATE(),                                      
         Sweeper_Co_Fin_Off_Info_Name=@UserID                                      
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';                                      
       END                 
                           
       ELSE IF @DataGroup='CorporateFinancials'                    
       BEGIN                    
        UPDATE Tracking_Data_Entry                    
        SET                    
         Sweeper_Corporate_Financials_Priority=1,                    
         Sweeper_Corporate_Financials_Priority_Dt=GETDATE(),                    
         Sweeper_Corporate_Financials_Priority_Name=@UserID                    
        WHERE Company_ID = @Company_ID AND FiscalYear = @FiscalYear;                                      
        SET @Result = '';                                      
        exec sp_PriorityReleaseDt @Company_ID,@FiscalYear                          
       END                                         
      ELSE                                      
       SET @Result = ''                                      
        exec sp_PriorityReleaseDt @Company_ID,@FiscalYear                                  
     END                                     
  END                                      
END 
```

**Behavior summary:** INSERT=True, UPDATE=True, IF-EXISTS branch=False

---

## `sp_Outstanding_Equity_Awards_IU_MAYA`

```sql
/*            
 =============================================       
-- Author:  Abhijit Deshmukh      
-- Create date: 10 Octomber 2019      
 -- Description: This SPROC insert or update Outstanding Equity Awards Detail.       
                 For the web Data Entry app.              
-- =============================================      
*/      
  
create PROCEDURE sp_Outstanding_Equity_Awards_IU_MAYA      
 
 (      
 
  @Officer_Outstanding_Equity_ID INT=NULL,        
  @Company_ID INT,      
  @FiscalYear INT,      
  @Equity_Type INT,       
  @Officer_ID INT,       
  @Grant_Date DATETIME=NULL,       
  @Number_Securities INT=NULL,       
  @Exercise_Price DECIMAL(18,5)=NULL,       
  @Expiration_Date DATETIME=NULL,       
  @Market_Value MONEY=NULL,       
  @Tracking_Stock_Ticker VARCHAR(10)=NULL,     
  @No_OEA_In_Proxy BIT=NULL ,    
  @Outstanding_Modification BIT=NULL     
      
 )      
  
AS      
 
BEGIN      

  UPDATE Company_FiscalYear    
 
  SET    
    No_OEA_In_Proxy=@No_OEA_In_Proxy ,  
    Outstanding_Modification=@Outstanding_Modification   

    WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear    
 
  IF(@Officer_Outstanding_Equity_ID IS NOT NULL)      

  BEGIN      
 
     IF(@Equity_Type=1 OR @Equity_Type=2 OR @Equity_Type=3)      

     BEGIN      
      UPDATE Officer_Outstanding_Equity      
 
  SET       
     Officer_ID=@Officer_ID,       
     Grant_Date=@Grant_Date,      
     Number_Securities=@Number_Securities,      
     Exercise_Price=@Exercise_Price,      
     Expiration_Date=@Expiration_Date,      
     Tracking_Stock_Ticker=@Tracking_Stock_Ticker      

  WHERE Officer_Outstanding_Equity_ID=@Officer_Outstanding_Equity_ID         

     END      
 
     ELSE IF(@Equity_Type=4 OR @Equity_Type=5)      
 
     BEGIN      
       UPDATE Officer_Outstanding_Equity      

  SET      
     Officer_ID=@Officer_ID,      
     Grant_Date=@Grant_Date,      
     Number_Securities=@Number_Securities,      
     Market_Value=@Market_Value,      
     Tracking_Stock_Ticker=@Tracking_Stock_Ticker      
  WHERE Officer_Outstanding_Equity_ID=@Officer_Outstanding_Equity_ID       
     END      
  END      
  ELSE      

  BEGIN       
    IF(@Equity_Type=1 OR @Equity_Type=2 OR @Equity_Type=3)      
   
    BEGIN      
     INSERT INTO Officer_Outstanding_Equity(Officer_ID,FiscalYear,Grant_Date,Equity_Type,Number_Securities,Exercise_Price,Expiration_Date,Tracking_Stock_Ticker)      
	           VALUES(@Officer_ID,@FiscalYear,@Grant_Date,@Equity_Type,@Number_Securities,@Exercise_Price,@Expiration_Date,@Tracking_Stock_Ticker)      
    END      

    ELSE IF(@Equity_Type=4 OR @Equity_Type=5)      

    BEGIN      
      INSERT INTO Officer_Outstanding_Equity(Officer_ID,FiscalYear,Grant_Date,Equity_Type,Number_Securities,Market_Value,Tracking_Stock_Ticker)      
              VALUES(@Officer_ID,@FiscalYear,@Grant_Date,@Equity_Type,@Number_Securities,@Market_Value,@Tracking_Stock_Ticker)      
    END      

  END      

END 
```

**Behavior summary:** INSERT=True, UPDATE=True, IF-EXISTS branch=False

---

## `sp_ExerciseandVested_U_MAYA`

```sql
      
  
        
  
/* =============================================            
  
 Author:  Abhijit Deshmukh.            
  
 Create date: SEPTEMBER 2019           
  
 Description: update Exercise and Vested data from Officer table.            
  
  
  
 Changelog:  
  
 added Company_FiscalYear update statement for No_EV_In_Proxy column update.    
  
 =============================================            
  
*/  
  
CREATE PROCEDURE [dbo].[sp_ExerciseandVested_U_MAYA]             
  
(       
  
 @Company_ID INT,            
 @FiscalYear INT,      
 @Officer_ID INT,      
 @Option_Shares_Acquired INT=NULL,      
 @Option_Value_Realized MONEY=NULL,      
 @Stock_Shares_Acquired INT=NULL,      
 @Stock_Value_Realized MONEY=NULL,      
 @Analyst_Notes VARCHAR(1000)=NULL,      
 @Internal_Notes VARCHAR(1000)=NULL,      
 @Notes_Comments_ID INT=NULL,      
 @Type INT,      
 @SubType INT,  
 @No_EV_In_Proxy BIT=NULL      
  
 )           
  
AS            
  
BEGIN            
               
     UPDATE Officer      
  
        SET Option_Shares_Acquired=@Option_Shares_Acquired,      
  
            Option_Value_Realized=@Option_Value_Realized,      
  
            Stock_Shares_Acquired=@Stock_Shares_Acquired,      
  
            Stock_Value_Realized=@Stock_Value_Realized      
  
        WHERE Officer_ID=@Officer_ID AND Company_ID=@Company_ID AND FiscalYear=@FiscalYear      
  
              
  
      IF(@Notes_Comments_ID IS NULL)      
  
      BEGIN      
  
          IF(@Analyst_Notes IS NOT NULL OR @Internal_Notes IS NOT NULL)      
  
          BEGIN      
  
    INSERT INTO Notes_Comments      
  
    (Company_ID,FiscalYear,Type,SubType,Comment,Note,Officer_ID,CreateDate)      
  
    VALUES(@Company_ID,@FiscalYear,@Type,@SubType,@Analyst_Notes,@Internal_Notes,@Officer_ID,GETDATE())      
  
    END        
  
      END      
  
      ELSE      
  
      BEGIN      
  
         UPDATE Notes_Comments      
  
         SET      
  
   Comment=@Analyst_Notes,      
  
   Note=@Internal_Notes      
  
   WHERE Notes_Comments_ID=@Notes_Comments_ID      
  
      END            
  
  
  
    UPDATE Company_FiscalYear      
  
      SET      
  
        No_EV_In_Proxy=@No_EV_In_Proxy      
  
      WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear     
  
END 
```

**Behavior summary:** INSERT=True, UPDATE=True, IF-EXISTS branch=False

---

## `sp_wk_PlanBasedAward_U_MAYA`

```sql
  
  
/*  
 Author: Abhijit Deshmukh 
 Created: 10/10/2019  
 Description: This SPROC updates the wk_PlanBasedAward columns using the ID. Depending on the Officer_Award_ID   
 parameters provided, will Update, or Insert.  
 For the web Data Entry app.  
 Changed GrantType to Award_Category in parameters and wk_PlanBasedAward.
 Officer_Awards MUST use Award_Category.
     
         Changelog  
======================================  
   
  
*/  
CREATE PROCEDURE [dbo].[sp_wk_PlanBasedAward_U_MAYA]  
    (  
      @ID INT,  
      @TagName NVARCHAR(50) = NULL,  
      @Officer_Awards_ID INT = 0,  
      @Officer_ID INT,  
      @Company_ID INT,  
      @FiscalYear INT,  
      @Award_Category INT = NULL,  
      @GrantDate DATETIME = NULL,  
      @ActionDate DATETIME = NULL,  
      @NonEquity_Threshold MONEY = NULL,  
      @NonEquity_Target MONEY = NULL,  
      @NonEquity_Maximum MONEY = NULL,  
      @Equity_Threshold MONEY = NULL,  
      @Equity_Target MONEY = NULL,  
      @Equity_Maximum MONEY = NULL,  
      @Option_Threshold MONEY = NULL,  
      @Option_Target MONEY = NULL,  
      @Option_Maximum MONEY = NULL,  
      @AllOther_Stock MONEY = NULL,  
      @AllOther_Options MONEY = NULL,  
      @Base_Price MONEY = NULL,  
      @GrantDate_Price MONEY = NULL,  
      @GDFV_Stock_Option MONEY = NULL  
    )  
AS   
    BEGIN  
        DECLARE @New_Officer_Award_ID INT ;       
  
-- Update wk_PlanBasedAward with changes from Web form  
        UPDATE  dbo.wk_PlanBasedAward  
        SET     TagName = @TagName,  
                Officer_Awards_ID = @Officer_Awards_ID,  
                Officer_ID = @Officer_ID,  
                Company_ID = @Company_ID,  
                FiscalYear = @FiscalYear,  
                Award_Category = @Award_Category,  
                GrantDate = @GrantDate,  
                ActionDate = @ActionDate,  
                NonEquity_Threshold = @NonEquity_Threshold,  
                NonEquity_Target = @NonEquity_Target,  
                NonEquity_Maximum = @NonEquity_Maximum,  
                Equity_Threshold = @Equity_Threshold,  
                Equity_Target = @Equity_Target,  
                Equity_Maximum = @Equity_Maximum,  
                Option_Threshold = @Option_Threshold,  
                Option_Target = @Option_Target,  
                Option_Maximum = @Option_Maximum,  
                AllOther_Stock = @AllOther_Stock,  
                AllOther_Options = @AllOther_Options,  
                Base_Price = @Base_Price,  
                GrantDate_Price = @GrantDate_Price,  
                GDFV_Stock_Option = @GDFV_Stock_Option  
        WHERE   ID = @ID  
          
-- Update or Insert into Officer depending if Officer Award ID was set.  
        IF ISNULL(@Officer_Awards_ID, 0) = 0   
            BEGIN  
                INSERT  INTO dbo.Officer_Awards  
                        (  
                          Officer_ID,  
                          FiscalYear,  
                          Award_Category,  
                          Grant_Date,  
                          Threshold,  
                          [Target],  
                          Maximum,  
                          Number_Securities,  
                          Exercise_Price,  
                          Grant_Date_Fair_Value,  
                          Parse_ID,  
                          PBA_Tag  
        
                        )  
                VALUES  (  
                          @Officer_ID,  
                          @FiscalYear,  
                          @Award_Category,  
                          @GrantDate,  
                          CASE @Award_Category  
                            WHEN 1 THEN @NonEquity_Threshold  
                            WHEN 2 THEN @Equity_Threshold  
                            WHEN 3 THEN @Option_Threshold  
                            ELSE 0  
          END,      -- Threshold  
                          CASE @Award_Category  
                            WHEN 1 THEN @NonEquity_Target  
                     WHEN 2 THEN @Equity_Target  
                            WHEN 3 THEN @Option_Target  
                            ELSE 0  
                          END,      -- Target  
                          CASE @Award_Category  
                            WHEN 1 THEN @NonEquity_Maximum  
                            WHEN 2 THEN @Equity_Maximum  
                            WHEN 3 THEN @Option_Maximum  
                            ELSE 0  
                          END,      -- Maximum  
                          CASE @Award_Category  
                            WHEN 4 THEN @AllOther_Stock  
                            WHEN 5 THEN @AllOther_Options  
                            ELSE 0  
                          END,      -- Number_Securities  
                          @Base_Price,  
                          @GDFV_Stock_Option,  
                          @ID,  
                          @TagName  
        
                        )  
      
                SET @New_Officer_Award_ID = SCOPE_IDENTITY() ;  
                SELECT  @New_Officer_Award_ID ;   
      
                UPDATE  dbo.wk_PlanBasedAward  
                SET     Officer_Awards_ID = @New_Officer_Award_ID  
                WHERE   ID = @ID  
  
            END  
        ELSE  -- Officer_Award row exists, so just update with new values  
            BEGIN  
  
                UPDATE  dbo.Officer_Awards  
                SET     Award_Category = @Award_Category,  
                        Grant_Date = @GrantDate,  
                        Threshold = CASE @Award_Category  
                                      WHEN 1 THEN @NonEquity_Threshold  
                                      WHEN 2 THEN @Equity_Threshold  
                                      WHEN 3 THEN @Option_Threshold  
                                      ELSE 0  
                                    END,  
                        [Target] = CASE @Award_Category  
                                     WHEN 1 THEN @NonEquity_Target  
                                     WHEN 2 THEN @Equity_Target  
                                     WHEN 3 THEN @Option_Target  
                                     ELSE 0  
                                   END,  
                        Maximum = CASE @Award_Category  
                                    WHEN 1 THEN @NonEquity_Maximum  
                                    WHEN 2 THEN @Equity_Maximum  
                                    WHEN 3 THEN @Option_Maximum  
                                    ELSE 0  
                                  END,  
                        Number_Securities = CASE @Award_Category  
                                              WHEN 4 THEN @AllOther_Stock  
                                              WHEN 5 THEN @AllOther_Options  
                                              ELSE 0  
                                            END,  
                        Exercise_Price = @Base_Price,  
                        Grant_Date_Fair_Value = @GDFV_Stock_Option,  
                        PBA_Tag = @TagName  
                WHERE   Officer_Awards_ID = @Officer_Awards_ID  
            END  
    END  
  
  

```

**Behavior summary:** INSERT=True, UPDATE=True, IF-EXISTS branch=False

---

## `sp_GenerateDirector_MAYA`

```sql


-- =============================================
-- Author:		Firoz
-- Create date:  Aug 2022
-- Description:	New SP_PROC Insert parsed BOD data into table.

--Try it 
--exec sp_GenerateDirector_MAYA 'dattased' ,'M' ,625 , 2019 ,0 ,0 ,null ,null ,null , null , null ,1254 ,10111,8787 ,1012 ,10121 ,null,null
-- =============================================
create PROCEDURE [dbo].[sp_GenerateDirector_MAYA] 
	-- Add the parameters for the stored procedure here
(@Director_Name varchar(250) = '',  
@Gender char(10) = '',  
@Company_ID int = 0,  
@FiscalYear int = 0,
@MasterNames_ID int = 0, 
@DirFlag bit = 0,  
@AGM_Date datetime = NULL, 
@titleDescCnt int = NULL, 
@Annual_Mtg_Price decimal(18, 2) = NULL,  
@Is_AGM_Disclosed bit = 0,  
@SourceDocument_ID int = NULL,
@FeesEarnedorPaid Money=NULL,
@StockAwards Money=NULL,
@OptionAwards Money=NULL,
@AllotherComp Money=NULL,
@Total Money=NULL,
@DirectorTag Nvarchar=NULL,
@FiscalYearEnd datetime = NULL) 
AS
BEGIN
DECLARE @Id integer  
  DECLARE @cnt integer  
  DECLARE @Director_Id integer  
  BEGIN TRANSACTION;  
    BEGIN TRY  
	
	declare  @GetMasterNameID int=0


	select @GetMasterNameID =MasterNames_ID from  BOD_DirectorComp  comp
	inner join BOD_Director_FiscalYear Bodfy
	on comp.Director_ID=Bodfy.Director_ID
	where Name =@Director_Name and comp.Company_ID=@Company_ID and comp.FiscalYear =@FiscalYear-1

	

      INSERT INTO BOD_Director_FiscalYear (MasterNames_ID, Company_ID, FiscalYear, AGM_Date, Annual_Mtg_Price, Is_AGM_Disclosed, SourceDocument_ID)  
            VALUES (@GetMasterNameID, @Company_ID, @FiscalYear, @AGM_Date, @Annual_Mtg_Price, @Is_AGM_Disclosed, @SourceDocument_ID)  
          SET @Director_Id = (SELECT 
            SCOPE_IDENTITY())  
          -- To insert values  Directors Bio (Other current directorship value) into BOD_OtherBoards table       
          INSERT INTO BOD_OtherBoards (Director_ID)  
            VALUES (@Director_Id)  
          --Insert Value in BOD_Director_Committees table          
          INSERT INTO BOD_Director_Committees (Director_ID,  
          Company_ID,  
          FiscalYear)  
            VALUES (@Director_Id, @Company_ID, @FiscalYear)  

			 INSERT INTO BOD_DirectorComp (Company_Id,FiscalYear,Name,FeesEarnedorPaid,stockawards,OptionAwards,allothercompensation,total,Director_Tag,Director_ID)
			 Values(@Company_ID, @FiscalYear,@Director_Name,@FeesEarnedorPaid,@StockAwards,@OptionAwards,@AllotherComp,@Total,@DirectorTag,@Director_Id)

			--Add fiscal year if not exists. Also update tracking.
			IF(NOT EXISTS(SELECT * FROM Financials WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear))        
			 BEGIN        
				INSERT INTO Financials(Company_ID,FiscalYear,FiscalYearEnd, CreatedBy,UpdatedDate,SprocName)        
				VALUES(@Company_ID,@FiscalYear,@FiscalYearEnd, 'MAYA',GETDATE(),'sp_GenerateDirector_MAYA')        
			 END 

			 IF(NOT EXISTS(SELECT * FROM Company_FiscalYear WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear))        
			 BEGIN        
				INSERT INTO Company_FiscalYear(Company_ID,FiscalYear,CreatedBy)        
				VALUES(@Company_ID,@FiscalYear,'MAYA')        
			 END        
        
			 IF(NOT EXISTS(SELECT * FROM Tracking_Data_Entry WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear))        
			 BEGIN        
				INSERT INTO Tracking_Data_Entry(Company_ID,FiscalYear,BoardPay_entered_Name,BoardPay_entered_Dt)        
				VALUES(@Company_ID,@FiscalYear,'MAYA',GETDATE())        
			 END  

			 IF(EXISTS(SELECT * FROM Tracking_Data_Entry WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear))        
			 BEGIN        
				update Tracking_Data_Entry
				Set
					BoardPay_entered_Name = 'MAYA',
					BoardPay_entered_Dt = GETDATE()       
				WHERE Company_ID=@Company_ID AND FiscalYear=@FiscalYear    
			 END  

      
    COMMIT TRANSACTION;  
  END TRY  
  BEGIN CATCH  
    ROLLBACK TRANSACTION;  
  END CATCH; 
END

```

**Behavior summary:** INSERT=True, UPDATE=True, IF-EXISTS branch=True

---

## `SP_Maya_Parsing_Company_Status`

```sql


-- =============================================
-- Author:  Vidushi    
-- Create date: 11/10/2022
-- Description:  Get ALl Parsing Data with comapany Status Live - Void

--Alter Procedure date: 16/03/2023
--Description:  Get ALl Parsing Data with comapany Status Live and Void and  Current Time -1 hour

--Alter Procedure date: 31/03/2023
--Description:  Get ALl Parsing Data with comapany Status Live and Live - Fresh - Void anf Void - Fresh

--Alter Procedure date: 06/04/2023
--Description:  Get ALl Parsing Data with comapany Status Live and Live - Fresh - Void anf Void - Fresh matching with Company_ID Maya Parsing Table.
--Alter Procedure date: 10/07/2023
--Description:  Adding two new columns as PM_Client and Peer_of_PM_Client.
--Description:  Adding  new columns as Priority in Maya_Parsing_Summary : 11 march 2026.
-- =============================================

CREATE PROCEDURE [dbo].[SP_Maya_Parsing_Company_Status]
AS
--DECLARE @curent_date date = getdate()
select
MPS.Company_ID,
MPS.CompanyName,
MPS.FiscalYear,
MPS.CIK,
MPS.Symbol,
CASE 
    WHEN MPS.Priority = 1 THEN '<b>True</b>'
    WHEN MPS.Priority = 0 THEN 'False'
    WHEN MPS.Priority IS NULL THEN 'False'
END AS Priority,
MPS.Fortune_1000,
MPS.Russell_3000,
MPS.MDG_Client,
MPS.Peer_Of_An_MDG_Client,
MPS.SP_400,
MPS.SP_500,
MPS.SP_600,
MPS.PM_Client,
MPS.Peer_of_PM_Client,
MPS.FiledDate,
MPS.FilingType,
MPS.Link,
MPS.Parsed_Date,
MPS.ProcessingType,
MPS.SCT_Parsed,
MPS.Officer_Parsed,
MPS.Vested_Parsed,
MPS.Outstanding_Equity_Parsed,
MPS.PBA_Parsed,
Case when (CFY.Completion_Status_Reasons_ID is null and CFY.Completion_Status is null) 
	then case When FR.CompanyName is not null then 'Live - Fresh Company' 
			else 'Live'
		 end

else 
		case When FR.CompanyName is not null then 'Void - Fresh Company' 
			else 'Void'
		end
end AS Company_Status
from Maya_Parsing_Summary MPS
left join Company_FiscalYear CFY on MPS.Company_ID = CFY.Company_ID and MPS.FiscalYear = CFY.FiscalYear
Left Join (
select 
CFY.Company_ID,
(select CompanyName from Company C where CFY.Company_ID = C.Company_ID) as CompanyName,
Count(CFY.Company_ID) as Company_Count
from Company_FiscalYear CFY
where 
CFY.FiscalYear in ((select Max(CFY1.FiscalYear) from Company_FiscalYear CFY1 where CFY.Company_ID = CFY1.Company_ID),
				   (select Max(CFY1.FiscalYear) from Company_FiscalYear CFY1 where CFY.Company_ID = CFY1.Company_ID)-1,
				   (select Max(CFY1.FiscalYear) from Company_FiscalYear CFY1 where CFY.Company_ID = CFY1.Company_ID)-2)
				   and CFY.Company_ID not in 
				   (select CFY.Company_ID from Company_FiscalYear CFY
						where 
						CFY.FiscalYear in ((select Max(CFY1.FiscalYear) from Company_FiscalYear CFY1 where CFY.Company_ID = CFY1.Company_ID),
											(select Max(CFY1.FiscalYear) from Company_FiscalYear CFY1 where CFY.Company_ID = CFY1.Company_ID)-1,
											(select Max(CFY1.FiscalYear) from Company_FiscalYear CFY1 where CFY.Company_ID = CFY1.Company_ID)-2)
											and CFY.Publish=1)
											and CFY.Company_ID <>0
				   Group by CFY.Company_ID
) FR on MPS.Company_ID = FR.Company_ID

where dateadd(hh,-1,getdate())< MPS.Parsed_Date--we added current date time parsed data for notification
--Convert(varchar,MPS.Parsed_Date,101) =  @curent_date 


```

**Behavior summary:** INSERT=False, UPDATE=False, IF-EXISTS branch=False

---

## `sp_Set_True_Tracker_Feed_Def14`

```sql

CREATE PROCEDURE [dbo].[sp_Set_True_Tracker_Feed_Def14]    
AS     
  BEGIN     
 update Tracker_Feed_Def14    
  set Value=1    
 where ID = 1   
    
  END    
    

```

**Behavior summary:** INSERT=False, UPDATE=True, IF-EXISTS branch=False

---

