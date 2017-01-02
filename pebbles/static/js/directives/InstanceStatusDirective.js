app.directive('instanceStatus', [function() {
    var UIDetails = {
        running: {
            iconClass: "glyphicon glyphicon-ok",
            description: "instance is ready"
        },
        failed: {
            iconClass: "glyphicon glyphicon-exclamation-sign",
            description: "instance failed"
        },
        queueing: {
            iconClass: "glyphicon glyphicon-cog fa-spin",
            description: "hang on tight, instance is waiting to be started"
        },
        provisioning: {
            iconClass: "glyphicon glyphicon-cog fa-spin",
            description: "almost there, instance is starting"
        },
        deleting: {
            iconClass: "glyphicon glyphicon-cog fa-spin",
            description: "instance is being deleted"
        },
        deleted: {
            iconClass: "glyphicon glyphicon-ban-circle",
            description: "instance deleted"
        },
        unknown: {
            iconClass: "glyphicon glyphicon-exclamation-sign",
            description: "instance state unknown"
        }
    };
    return {
        restrict: 'E',
        scope: false,
        link: function(scope, element, attrs) {
            statusDetails = UIDetails[scope.instance.state];
            if (! statusDetails) {
                statusDetails = UIDetails.unknown;
            }
            scope.iconClass = statusDetails.iconClass;
            scope.description = statusDetails.description;
        },
        templateUrl: 'partials/instance_state.html'
    };
}]);
