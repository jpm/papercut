ALTER TABLE forums ADD nntp_group_name VARCHAR(30);
ALTER TABLE forums ADD UNIQUE (nntp_group_name); 
