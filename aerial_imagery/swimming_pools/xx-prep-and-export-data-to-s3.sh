#!/usr/bin/env bash

SECONDS=0*

# get the directory this script is running from
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# ---------------------------------------------------------------------------------------------------------------------
# edit these to taste - NOTE: you can't use "~" for your home folder, Postgres doesn't like it
# ---------------------------------------------------------------------------------------------------------------------

AWS_PROFILE="default"
OUTPUT_FOLDER="/Users/$(whoami)/tmp/image-classification"

echo "---------------------------------------------------------------------------------------------------------------------"
echo "create subset tables to speed up export, copy and import"
echo "---------------------------------------------------------------------------------------------------------------------"

psql -d geo -f ${SCRIPT_DIR}/xx_prep_gnaf_cad_tables.sql

echo "---------------------------------------------------------------------------------------------------------------------"
echo "dump postgres tables to a local folder"
echo "---------------------------------------------------------------------------------------------------------------------"

mkdir -p "${OUTPUT_FOLDER}"
/Applications/Postgres.app/Contents/Versions/13/bin/pg_dump -Fc -d geo -t data_science.aus_cadastre_boundaries_nsw -t data_science.address_principals_nsw -p 5432 -U postgres -f "${OUTPUT_FOLDER}/gnaf-cad.dmp" --no-owner
echo "GNAF & Cad exported to dump file"

echo "---------------------------------------------------------------------------------------------------------------------"
echo "copy training data & Postgres dump file to AWS S3"
echo "---------------------------------------------------------------------------------------------------------------------"

aws --profile=${AWS_PROFILE} s3 sync "/Users/$(whoami)/Downloads/Swimming Pools with Labels" s3://image-classification-swimming-pools/training/swimming-pools/
aws --profile=${AWS_PROFILE} s3 sync ${OUTPUT_FOLDER} s3://image-classification-swimming-pools/geoscape/ --exclude "*" --include "*.dmp"

echo "-------------------------------------------------------------------------"
duration=$SECONDS
echo " End time : $(date)"
echo " Data export took $((duration / 60)) mins"
echo "----------------------------------------------------------------------------------------------------------------"