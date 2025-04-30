import streamlit as st
import pandas as pd
from simpleAnanlysis import load_data, identify_unique_restaurants, analyze_selected_restaurants
import os
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go

# Set page config
st.set_page_config(
    page_title="Food Safety Analysis Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
    <style>
    .main {
        padding: 2rem;
    }
    .stProgress > div > div > div {
        background-color: #4CAF50;
    }
    </style>
    """, unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.title("Food Safety Analysis")
    st.write("---")
    st.write("Upload your Excel file and analyze food safety compliance across different checklist types.")
    st.write("---")
    
    # File uploader in sidebar
    uploaded_file = st.file_uploader("Choose an Excel file", type=['xlsx', 'xls'])
    
    if uploaded_file is not None:
        st.success("File uploaded successfully!")
        st.write("---")
        
        # API Key input in sidebar
        api_key = st.text_input("Enter your OpenAI API Key", type="password")
        st.write("---")

# Main content
if uploaded_file is not None:
    try:
        # Save the uploaded file temporarily
        with open("temp_file.xlsx", "wb") as f:
            f.write(uploaded_file.getvalue())
        
        # Load the data
        df = load_data("temp_file.xlsx")
        st.success(f"Successfully loaded data with {len(df)} rows and {df.shape[1]} columns")
        
        # Identify unique checklist types
        unique_checklists = identify_unique_restaurants(df)
        
        # Create a multi-select for checklist types
        selected_checklists = st.multiselect(
            "Select checklist types to analyze",
            options=unique_checklists,
            default=unique_checklists[:1] if unique_checklists else None
        )
        
        if selected_checklists and api_key:
            if st.button("Start Analysis", type="primary"):
                with st.spinner("Analyzing images... This may take a while."):
                    # Progress bar
                    progress_bar = st.progress(0)
                    
                    # Run analysis
                    analyzed_df = analyze_selected_restaurants(df, selected_checklists, api_key)
                    
                    # Display results
                    st.header("Analysis Results")
                    
                    # Create tabs for different views
                    tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Checklist Details", "Quality Issues", "Raw Data"])
                    
                    with tab1:
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            # Overall compliance status with Plotly
                            compliance_counts = analyzed_df['compliance_status'].value_counts()
                            fig_compliance = px.pie(
                                values=compliance_counts.values,
                                names=compliance_counts.index,
                                title="Overall Compliance Status",
                                color_discrete_sequence=px.colors.qualitative.Set3
                            )
                            st.plotly_chart(fig_compliance, use_container_width=True)
                        
                        with col2:
                            # Severity levels with Plotly
                            severity_counts = analyzed_df['severity_level'].value_counts()
                            fig_severity = px.bar(
                                x=severity_counts.index,
                                y=severity_counts.values,
                                title="Severity Levels Distribution",
                                labels={'x': 'Severity', 'y': 'Count'},
                                color=severity_counts.values,
                                color_continuous_scale='RdYlGn_r'
                            )
                            st.plotly_chart(fig_severity, use_container_width=True)
                        
                        # Tags analysis
                        st.subheader("Top Tags Analysis")
                        all_tags = []
                        for tag_str in analyzed_df['tags'].dropna():
                            all_tags.extend([tag.strip() for tag in tag_str.split(',')])
                        
                        from collections import Counter
                        top_tags = Counter(all_tags).most_common(10)
                        
                        fig_tags = px.bar(
                            x=[tag[0] for tag in top_tags],
                            y=[tag[1] for tag in top_tags],
                            title="Top 10 Tags",
                            labels={'x': 'Tag', 'y': 'Count'},
                            color=[tag[1] for tag in top_tags],
                            color_continuous_scale='Viridis'
                        )
                        st.plotly_chart(fig_tags, use_container_width=True)
                    
                    with tab2:
                        # Checklist-specific analysis
                        for checklist in selected_checklists:
                            st.subheader(f"Analysis for {checklist}")
                            checklist_df = analyzed_df[analyzed_df['checklist_type'] == checklist]
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                # Compliance status for this checklist
                                checklist_compliance = checklist_df['compliance_status'].value_counts()
                                fig_checklist_compliance = px.pie(
                                    values=checklist_compliance.values,
                                    names=checklist_compliance.index,
                                    title=f"Compliance Status - {checklist}",
                                    color_discrete_sequence=px.colors.qualitative.Set3
                                )
                                st.plotly_chart(fig_checklist_compliance, use_container_width=True)
                            
                            with col2:
                                # Severity levels for this checklist
                                checklist_severity = checklist_df['severity_level'].value_counts()
                                fig_checklist_severity = px.bar(
                                    x=checklist_severity.index,
                                    y=checklist_severity.values,
                                    title=f"Severity Levels - {checklist}",
                                    labels={'x': 'Severity', 'y': 'Count'},
                                    color=checklist_severity.values,
                                    color_continuous_scale='RdYlGn_r'
                                )
                                st.plotly_chart(fig_checklist_severity, use_container_width=True)
                            
                            # Display detailed results in an expandable section
                            with st.expander("View Detailed Results"):
                                st.dataframe(
                                    checklist_df[['question', 'compliance_status', 'severity_level', 'explanation', 'improvement_suggestions']],
                                    use_container_width=True
                                )
                    
                    with tab3:
                        # Image quality issues
                        quality_issues = analyzed_df['image_quality_issues'].value_counts()
                        fig_quality = px.bar(
                            x=quality_issues.index,
                            y=quality_issues.values,
                            title="Image Quality Issues Distribution",
                            labels={'x': 'Issue Type', 'y': 'Count'},
                            color=quality_issues.values,
                            color_continuous_scale='RdYlBu'
                        )
                        st.plotly_chart(fig_quality, use_container_width=True)
                        
                        # Display images with quality issues
                        st.subheader("Images with Quality Issues")
                        quality_issues_df = analyzed_df[analyzed_df['image_quality_issues'].str.contains('too_dark|too_blurry', na=False)]
                        st.dataframe(
                            quality_issues_df[['checklist_type', 'question', 'image_quality_issues']],
                            use_container_width=True
                        )
                    
                    with tab4:
                        # Raw data view with filtering options
                        st.subheader("Raw Data Analysis")
                        
                        # Add filters
                        col1, col2 = st.columns(2)
                        with col1:
                            compliance_filter = st.multiselect(
                                "Filter by Compliance Status",
                                options=analyzed_df['compliance_status'].unique()
                            )
                        with col2:
                            severity_filter = st.multiselect(
                                "Filter by Severity Level",
                                options=analyzed_df['severity_level'].unique()
                            )
                        
                        # Apply filters
                        filtered_df = analyzed_df
                        if compliance_filter:
                            filtered_df = filtered_df[filtered_df['compliance_status'].isin(compliance_filter)]
                        if severity_filter:
                            filtered_df = filtered_df[filtered_df['severity_level'].isin(severity_filter)]
                        
                        # Display filtered data
                        st.dataframe(filtered_df, use_container_width=True)
                    
                    # Download button for results
                    output_file = f"analysis_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                    analyzed_df.to_excel(output_file, index=False)
                    with open(output_file, "rb") as f:
                        st.download_button(
                            label="Download Analysis Results",
                            data=f,
                            file_name=output_file,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    
                    # Clean up temporary file
                    os.remove("temp_file.xlsx")
                    if os.path.exists(output_file):
                        os.remove(output_file)
    
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        if os.path.exists("temp_file.xlsx"):
            os.remove("temp_file.xlsx") 