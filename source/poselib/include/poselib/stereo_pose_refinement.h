/**********************************************************************************************************
FILE: stereo_pose_refinement.h

PLATFORM: Windows 7, MS Visual Studio 2010, OpenCV 3.2

CODE: C++

AUTOR: Josef Maier, AIT Austrian Institute of Technology

DATE: October 2017

LOCATION: TechGate Vienna, Donau-City-Stra?e 1, 1220 Vienna

VERSION: 1.0

DISCRIPTION: This file provides functions for pose refinement with multiple stereo pairs
**********************************************************************************************************/

#pragma once

#include "opencv2/highgui/highgui.hpp"
#include "poselib/glob_includes.h"
#include "poselib/pose_estim.h"
#include "poselib/pose_helper.h"
#include "poselib/nanoflannInterface.h"
#include <list>
#include <unordered_map>
#include <memory>
#include <Eigen/Core>

#include "poselib/poselib_api.h"

namespace poselib
{

	/* --------------------------- Defines --------------------------- */

	/*struct POSELIB_API ConfigMatching
	{
		ConfigMatching() : img1(NULL),
			img2(NULL),
			histEqual(false),
			f_detect("FAST"),
			d_extr("FREAK"),
			matcher("GMBSOF"),
			nmsIdx(""),
			nmsQry(""),
			f_nr(8000),
			noRatiot(false),
			refineVFC(false),
			DynKeyP(false),
			subPixRef(1),
			showNr_matches(50),
			verbose(7)
		{}

		cv::Mat* img1;
		cv::Mat* img2;
		bool histEqual;
		std::string f_detect;
		std::string d_extr;
		std::string matcher;
		std::string nmsIdx;
		std::string nmsQry;
		int f_nr;
		bool noRatiot;
		bool refineVFC;
		bool refineSOF;
		bool DynKeyP;
		int subPixRef;
		int showNr_matches;
		int verbose;	
	};*/

	// problem specific/data-related parameters: essential matrix
	struct POSELIB_API ConfigPoseEstimation
	{
		ConfigPoseEstimation() : dist0_8(NULL),
			dist1_8(NULL),
			K0(NULL),
			K1(NULL),
			th_pix_user(0.8),
			autoTH(false),
			Halign(0),
			RobMethod("USAC"),
			refineMethod(poselib::RefinePostAlg::PR_NO_REFINEMENT),
			refineRTold(false),
			kneipInsteadBA(false),
			BART(0),
			verbose(7),
			minStartAggInlRat(0.2),
			relInlRatThLast(0.35),
			relInlRatThNew(0.15),
			minInlierRatSkip(0.38),
			relMinInlierRatSkip(0.7),
			maxSkipPairs(5),
			minInlierRatioReInit(0.55),
			minPtsDistance(3.f)
		{}

		cv::Mat* dist0_8;//Distortion paramters in OpenCV format with 8 parameters for the first/left image
		cv::Mat* dist1_8;//Distortion paramters in OpenCV format with 8 parameters for the second/right image
		cv::Mat* K0;//Camera matrix of the first/left camera
		cv::Mat* K1;//Camera matrix of the second/right camera
		double th_pix_user;//Threshold for robust refinement in pixels
		bool autoTH;//If the essentila matrix should be estimated using an automatic threshold estimation and ARRSAC
		int Halign;//If the essentila matrix should be estimated using homography alignment
		std::string RobMethod;//USAC,RANSAC,ARRSAC,LMEDS
		int refineMethod;//Choose the refinement algorithm (not necessary for USAC). For details see enum RefinePostAlg
		bool refineRTold;//If true, the old refinement algorithm based on the 8pt algorithm and pseudo-huber weights
		bool kneipInsteadBA;//If true, Kneips Eigen solver is used instead of bundle adjustment (no additional refinement beforehand)
		int BART;//Optional bundle adjustment (BA): 0: no BA, 1: BA for extrinsics and structure only, 2: BA for intrinsics, extrinsics, and structure
		int verbose;//Verbosity level (max:7)
		double minStartAggInlRat;//Threshold on the inlier ratio for the first pose estimation. Below this threshold the correspondences will be discarded and not used in the next iteration.
		double relInlRatThLast;//Relative threshold (th = (1 - relInlRatThLast) * last_inl_rat) on the inlier ratios to decide if a new robust estimation is necessary (for comparison, the inlier ratio of the last image pair "last_inl_rat" is used)
		double relInlRatThNew;//Relative threshold (th = (1 - relInlRatThNew) * old_inl_rat) on the inlier ratios of the new image pair with the old and new (with robust estimation) Essential matrix. Is only used if a new robust estimation was performed (see relInlRatThLast)
		double minInlierRatSkip;//Absolute threshold on the inlier ratio for new image pairs if the old essential matrix E differs from the new one (estimated with a robust method). Below this threshold, a fall-back threshold estimated by relMinInlierRatSkip can be used, if the resulting threshold is smaller minInlierRatSkip.
		double relMinInlierRatSkip;//Relative threshold (th =  relMinInlierRatSkip * last_valid_inlier_rat) on the inlier ratio for new image pairs compared to the last valid (estimation of E with multiple image pairs) if the old essential matrix E differs from the new one (estimated with a robust method). Below this threshold the old pose is restored.
		size_t maxSkipPairs;//Maximum number of times the new Essential matrix E is discarded and restored by the old one (see minInlierRatSkip). If more E's are discarded, the whole system is reinitialized.
		double minInlierRatioReInit;//If the new pose differs from the old, the whole system is reinitialized if the inlier ratio with the new pose is above this value
		float minPtsDistance;//Minimum distance between points for insertion into the correspondence pool
	};

	typedef struct CoordinateProps
	{
		CoordinateProps() : pt1(0,0),
			pt2(0, 0),
			ptIdx(0),
			poolIdx(0),
			Q(0,0,0),
			Q_tooFar(true),
			age(0),
			descrDist(0),
			keyPResponses{0,0},
			nrFound(1),
			meanSampsonError(DBL_MAX),
			SampsonErrors(std::vector<double>())
		{}

		cv::Point2f pt1;//Keypoint position in first/left image
		cv::Point2f pt2;//Keypoint position in second/right image
		size_t ptIdx;//Index which points to the corresponding points in the camera coordinate system
		size_t poolIdx;//Key of the map that holds the iterators to the list entries of this data structure
		cv::Point3d Q;//Triangulated 3D point
		bool Q_tooFar;//If the z-coordinate of Q is too large, this falue is true. Too far Q's should be excluded in BA to be more stable.
		size_t age;//For how many estimation iterations is this correspondence alive
		float descrDist;//Descriptor distance
		float keyPResponses[2];//Response of corresponding keypoints in the first and second image
		size_t nrFound;//How often the correspondence was found in different image pairs
		double meanSampsonError;//Mean sampson Error over all available E within age
		std::vector<double> SampsonErrors;//Sampson Error for every E this correspondence was used to calculate it
	} CoordinateProps;

	//typedef Eigen::Matrix<double, Eigen::Dynamic, 2, Eigen::RowMajor> EMatDouble2;

	/* --------------------- Function prototypes --------------------- */


	/* --------------------------- Classes --------------------------- */

	class POSELIB_API StereoRefine
	{
	private:
		ConfigPoseEstimation cfg_pose;
		poselib::ConfigUSAC cfg_usac;
		double pixToCamFact;
		int nrEstimation;
		size_t skipCount;
		std::vector<cv::Point2f> points1new, points2new;//Undistorted point correspondences in the camera coordinate system
		cv::Mat points1newMat, points2newMat;//The same as points1new and points2new but double values in cv::Mat format
		cv::Mat points1newMat_tmp, points2newMat_tmp;//The same as points1newMat and points2newMat but holds also the correspondences that were filtered out
		cv::Mat points1Cam, points2Cam;//Undistorted point correspondences in the camera coordinate system of all vaild image pairs
		double th;//Inlier threshold
		double th2;//Squared inlier threshold
		double t_mea; //Time measurement
		double t_oa; //Overall time
		float descrDist_max;//Maximum observed descriptor distance in the data
		float keyPRespons_max; //Maximum observed keypoint response in the data
		cv::Mat E_new; //Newest essential matrix
		cv::Mat mask_E_new; //Newest mask using E only for the newest image pair
		cv::Mat mask_Q_new; //Newest mask using E and triangulated 3D points (excludes correspondences too far away) for the newest image pair
		size_t nr_inliers_new;//Number of inliers for the newest image pair
		size_t nr_corrs_new;//Number of initial correspondences of the newest image pair
		cv::Mat mask_E_old; //Mask using E only for all corresponding keypoints of the preceding image pairs (excluding the newest)
		cv::Mat mask_Q_old; //Mask using E and triangulated 3D points (excludes correspondences too far away) for all corresponding keypoints of the preceding image pairs (excluding the newest)
		cv::Mat Q;//3D points of latest image pair
		cv::Mat R_new; //Newest rotation matrix
		cv::Mat t_new; //Newest translation vector

		std::list<CoordinateProps> correspondencePool;//Holds all correspondences and their properties over the last valid image pairs
		std::unordered_map<size_t, std::list<CoordinateProps>::iterator> correspondencePoolIdx;//Stores the iterator to every correspondencePool element. The key value is an continous index necessary for nanoflann
		size_t corrIdx;//Continous index starting with 0 counting all correspondences that were ever inserted into correspondencePool. The index is resetted when the KD tree is resetted.
		std::unique_ptr<keyPointTree> kdTreeLeft;//KD-tree using nanoflann holding the keypoint coordinates of the left valid keypoints
		std::vector<size_t> deletionIdxs;//Holds indexes of point correspondences to be deleted

		struct CoordinatePropsNew
		{
			CoordinatePropsNew(cv::Point2f pt1_, cv::Point2f pt2_, float descrDist_, float response1, float response2, double sampsonError_) : pt1(pt1_),
				pt2(pt2_),
				descrDist(descrDist_),
				keyPResponses{ response1, response2 },
				sampsonError(sampsonError_)
			{}

			cv::Point2f pt1;//Keypoint position in first/left image
			cv::Point2f pt2;//Keypoint position in second/right image
			float descrDist;//Descriptor distance
			float keyPResponses[2];//Response of corresponding keypoints in the first and second image
			double sampsonError;//Sampson Error
		};

		struct poseHist
		{
			poseHist(cv::Mat E_, cv::Mat R_, cv::Mat t_) : E(E_),
				R(R_),
				t(t_)
			{}

			cv::Mat E;
			cv::Mat R;
			cv::Mat t;
		};
		std::vector<poseHist> pose_history;//Holds all valid poses over the last estimations
		std::vector<double> inlier_ratio_history;//Holds the inlier ratios for the last image pairs
		std::vector<statVals> errorStatistic_history;//Holds statics of the Sampson errors for the last image pairs

	public:
		
		StereoRefine(ConfigPoseEstimation cfg_pose_) :
			cfg_pose(cfg_pose_)	{
			pixToCamFact = 4.0 / (std::sqrt(2.0) * (cfg_pose_.K0->at<double>(0, 0) + cfg_pose_.K0->at<double>(1, 1) + cfg_pose_.K1->at<double>(0, 0) + cfg_pose_.K1->at<double>(1, 1)));
			nrEstimation = 0;
			skipCount = 0;
			th = cfg_pose_.th_pix_user * pixToCamFact; //Inlier threshold
			th2 = th * th;
			checkInlRatThresholds();
			corrIdx = 0;
			t_mea = 0;
			t_oa = 0;
			descrDist_max = 0;
			keyPRespons_max = 0;
		}

		void setNewParameters(ConfigPoseEstimation cfg_pose_);

		int addNewCorrespondences(std::vector<cv::DMatch> matches, std::vector<cv::KeyPoint> kp1, std::vector<cv::KeyPoint> kp2, poselib::ConfigUSAC cfg);

	private:

		int robustPoseEstimation();
		int addCorrespondencesToPool(std::vector<cv::DMatch> matches, std::vector<cv::KeyPoint> kp1, std::vector<cv::KeyPoint> kp2);
		size_t getInliers(cv::Mat E, cv::Mat & p1, cv::Mat & p2, cv::Mat & mask, std::vector<double> & error);
		void clearHistoryAndPool();
		void checkInlRatThresholds();
		int filterNewCorrespondences(std::vector<cv::DMatch> & matches, std::vector<cv::KeyPoint> kp1, std::vector<cv::KeyPoint> kp2, std::vector<double> error);
		bool compareCorrespondences(CoordinatePropsNew &newCorr, CoordinateProps &oldCorr);
		int poolCorrespondenceDelete(std::vector<size_t> delete_list);
	};
	
}
