# 2. Process Wellsky (Revised for Wellsky .xls/html exports)
        try:
            # Wellsky .xls files are often actually HTML tables. 
            # This reads them correctly.
            well_tables = pd.read_html(well_file)
            df_well = well_tables[0]
        except:
            # Fallback for true CSVs with inconsistent delimiters
            well_file.seek(0) # Reset file pointer
            df_well = pd.read_csv(well_file, header=None, sep=None, engine='python', encoding='latin1')
        
        wellsky_list = []
        current_key = None
        
        # Determine if we have column names or numbers based on read method
        # We'll iterate by index to be safe
        for i in range(len(df_well)):
            row = df_well.iloc[i]
            
            # Identify a client header row
            # Usually has the ID in the 2nd column (index 1)
            val_col1 = str(row.iloc[1])
            if len(val_col1) > 5 and val_col1 != "nan":
                # Adjusted indices: Last Name usually col 5, First Name col 10
                last = str(row.iloc[5]) if len(row) > 5 else ""
                first = str(row.iloc[10]) if len(row) > 10 else ""
                current_key = clean_key(f"{last}{first}")
            
            # Identify the Sub Total row
            # Checking columns 17 or 18 for the words 'Sub Total'
            row_str = " ".join([str(x) for x in row.values])
            if "Sub Total" in row_str and current_key:
                # Find the first numeric value after 'Sub Total'
                # Usually in column 19 (index 18 or 19)
                nums = []
                for val in row.values:
                    try:
                        n = float(val)
                        if n > 0: nums.append(n)
                    except: continue
                
                final_val = nums[0] if nums else 0
                wellsky_list.append({'MatchKey': current_key, 'Wellsky': final_val})
        
        df_well_final = pd.DataFrame(wellsky_list).groupby('MatchKey').sum().reset_index()
