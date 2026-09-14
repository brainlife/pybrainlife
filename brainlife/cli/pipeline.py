# /**
#  * @apiGroup Pipeline Rules
#  * @api {post} /rule                Register new rule
#  *
#  * @apiDescription                  Register a new pipeline rule.
#  *
#  * @apiParam {String} name          Rule name
#  * @apiParam {String} desc          Rule description
#  * @apiParam {String} project       Project ID
#  * @apiParam {Object} input_tags    Input Tags
#  * @apiParam {Object} output_tags   Output Tags
#  * @apiParam {Object} input_project_override
#  *                                  Input project override
#  * @apiParam {String} app           Application ID
#  * @apiParam {String} branch        Application branch to use
#  * @apiParam {Boolean} active       Active flag
#  * @apiParam {String} subject_match Subject match
#  * @apiParam {String} session_match Session match
#  * @apiParam {Object} config        Application configuration
#  *
#  * @apiHeader {String} authorization
#  *                                  A valid JWT token "Bearer: xxxxx"
#  *
#  * @apiSuccess {Object}             Created rule object
